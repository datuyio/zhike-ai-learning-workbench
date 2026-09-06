from pathlib import Path

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api.v1.router import api_router
from app.api.ws import ws_router
from app.core.config import load_project_env, settings

# 启动即把 .env 注入进程环境（模型网关等模块通过 os.getenv 读取 API Key）
load_project_env()
from app.core.tracing import new_trace_id, reset_trace_id, set_trace_id
from app.services.model_gateway.health import model_gateway_health_scheduler
from app.services.model_gateway.reload import model_gateway_reload_listener
from app.services.resource.pipeline_scheduler import resource_generation_scheduler


logger = logging.getLogger(__name__)


class HealthFeatures(BaseModel):
    """健康检查中暴露的关键后端能力开关。"""

    course_ai_context: bool
    course_extracted_qa: bool
    native_chunks: bool
    document_file_preview: bool


class HealthResponse(BaseModel):
    """系统健康检查响应契约。"""

    status: str
    app: str
    features: HealthFeatures


def create_app() -> FastAPI:
    """创建 FastAPI 应用并注册路由、静态资源和后台任务。"""
    from app.services.model_gateway.provider_icons import ensure_default_icons, icons_dir
    from app.services.site_settings import ensure_site_assets_dir

    settings.validate_runtime_security()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """启动和关闭应用级后台任务。"""
        ensure_default_icons()
        Path(icons_dir()).mkdir(parents=True, exist_ok=True)
        ensure_site_assets_dir()
        app.state.model_gateway_reload_task = asyncio.create_task(model_gateway_reload_listener())
        app.state.model_gateway_health_task = asyncio.create_task(model_gateway_health_scheduler())
        app.state.resource_generation_task = asyncio.create_task(resource_generation_scheduler())
        try:
            yield
        finally:
            for attr in (
                "model_gateway_reload_task",
                "model_gateway_health_task",
                "resource_generation_task",
            ):
                task = getattr(app.state, attr, None)
                if task:
                    task.cancel()

    app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """统一处理未捕获异常，对外隐藏内部细节并保留 trace id。"""
        if isinstance(exc, HTTPException):
            raise exc
        trace_id = request.headers.get("X-Trace-Id") or new_trace_id("error")
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "服务器处理失败，请稍后重试或联系管理员。",
                    "trace_id": trace_id,
                }
            },
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _app_route_paths() -> set[str]:
        """收集已注册路由路径，用于健康检查暴露功能开关。"""
        return {getattr(route, "path", "") for route in app.routes}

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health_check() -> HealthResponse:
        """返回应用健康状态和关键功能路由注册情况。"""
        prefix = settings.API_V1_PREFIX
        paths = _app_route_paths()
        return HealthResponse(
            status="ok",
            app=settings.APP_NAME,
            features=HealthFeatures(
                course_ai_context=f"{prefix}/courses/{{course_id}}/ai-context" in paths,
                course_extracted_qa=f"{prefix}/courses/{{course_id}}/extracted-qa" in paths,
                native_chunks=f"{prefix}/admin/documents/{{document_id}}/native-chunks" in paths,
                document_file_preview=f"{prefix}/admin/documents/{{document_id}}/file" in paths,
            ),
        )

    @app.middleware("http")
    async def trace_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """为每个 HTTP 请求设置 trace id，并在响应头回传。"""
        trace_id = request.headers.get("X-Trace-Id") or new_trace_id("http")
        token = set_trace_id(trace_id)
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            reset_trace_id(token)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(ws_router, prefix="/ws")

    ensure_default_icons()
    app.mount(
        f"{settings.API_V1_PREFIX}/static/provider-icons",
        StaticFiles(directory=str(icons_dir())),
        name="provider-icons",
    )
    app.mount(
        f"{settings.API_V1_PREFIX}/static/site-assets",
        StaticFiles(directory=str(ensure_site_assets_dir())),
        name="site-assets",
    )

    return app


app = create_app()
