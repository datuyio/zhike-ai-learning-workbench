from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret
from app.core.tracing import get_trace_id
from app.models import Course, ModelCallLog, ModelProvider, ModelProviderHealth
from app.services.model_gateway.http_client import model_gateway_client_kwargs


IMAGE_PROVIDER_TYPES = {"image", "image_generation"}
OPENAI_IMAGE_PROTOCOLS = {"openai_compatible", "openai_images", "openai_image"}
FAL_QUEUE_PROTOCOLS = {"fal_queue", "fal"}
CUSTOM_SYNC_PROTOCOLS = {"custom_http_sync", "http_json", "custom_sync"}
CUSTOM_ASYNC_PROTOCOLS = {"custom_http_async", "http_async", "custom_async"}

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ImageProviderConfig:
    """图片生成供应商配置。"""

    id: uuid.UUID | None
    provider: str
    display_name: str
    provider_type: str
    base_url: str
    api_key: str | None
    key_source: str
    protocol: str
    model: str
    cost_config: dict[str, Any]
    meta_json: dict[str, Any]


@dataclass(slots=True)
class ImageGenerationInput:
    """单张教学图生成入参。"""

    prompt: str
    aspect_ratio: str
    style_preset: str
    provider_code: str | None = None
    course_slug: str | None = None
    agent_name: str = "Image generation"
    reference_paths: list[str] | None = None
    extra_params: dict[str, Any] | None = None


@dataclass(slots=True)
class GeneratedImage:
    """图片供应商统一返回结构。"""

    url: str | None
    bytes_data: bytes | None
    width: int | None
    height: int | None
    mime_type: str
    provider: str
    model: str
    prompt: str
    revised_prompt: str | None
    raw_params: dict[str, Any]


class ImageProviderUnavailable(RuntimeError):
    """没有可用图片生成供应商。"""


def resolve_image_size(aspect_ratio: str) -> str:
    """将前端比例转换为常见图片模型可接受的尺寸。"""
    normalized = (aspect_ratio or "1:1").strip()
    if normalized in {"16:9", "4:3", "3:2", "landscape"}:
        return "1536x1024"
    if normalized in {"9:16", "3:4", "2:3", "portrait"}:
        return "1024x1536"
    return "1024x1024"


def detect_image_size(data: bytes) -> tuple[int | None, int | None, str]:
    """从常见图片头部读取尺寸，避免额外引入图像处理依赖。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return width, height, "image/png"
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            segment_length = int.from_bytes(data[index + 2:index + 4], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(data[index + 5:index + 7], "big")
                width = int.from_bytes(data[index + 7:index + 9], "big")
                return width, height, "image/jpeg"
            index += max(segment_length + 2, 2)
        return None, None, "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return None, None, "image/webp"
    return None, None, "image/png"


def _image_generations_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/images/generations"):
        return root
    return f"{root}/images/generations"


def _bearer_auth_header(api_key: str) -> str:
    token = api_key.strip()
    if token.lower().startswith(("bearer ", "key ")):
        return token
    return f"Bearer {token}"


def _extract_json_path(payload: dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, list):
            if not part.isdigit():
                return None
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


class ImageGenerationService:
    """通过模型网关配置调用真实图片生成供应商。"""

    _ENV_KEY_CANDIDATES: dict[str, tuple[str, ...]] = {
        "openai": ("OPENAI_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "openai_image": ("OPENAI_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "openai_images": ("OPENAI_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "fal": ("FAL_KEY", "FAL_API_KEY", "MODEL_GATEWAY_API_KEY"),
        "fal_ai": ("FAL_KEY", "FAL_API_KEY", "MODEL_GATEWAY_API_KEY"),
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    def has_configured_provider(self, provider_code: str | None = None) -> bool:
        """判断是否存在可调用的图片生成供应商。"""
        try:
            config = self._select_provider(provider_code)
        except ImageProviderUnavailable:
            return False
        return bool(config.api_key and config.model)

    async def generate(self, payload: ImageGenerationInput) -> GeneratedImage:
        """生成单张图片，并转换为统一返回结构。"""
        config = self._select_provider(payload.provider_code)
        started = time.perf_counter()
        if not config.api_key:
            raise ImageProviderUnavailable("ImageProvider 未配置 API Key，请在模型网关或环境变量中配置图片生成密钥。")
        if not config.model:
            raise ImageProviderUnavailable("ImageProvider 未配置图片生成模型，请填写 image_model 或图片模型名称。")

        protocol = config.protocol.strip().lower()
        try:
            if protocol in OPENAI_IMAGE_PROTOCOLS:
                result = await self._generate_openai_compatible(config, payload)
            elif protocol in FAL_QUEUE_PROTOCOLS or config.provider.startswith("fal"):
                result = await self._generate_fal_queue(config, payload)
            elif protocol in CUSTOM_ASYNC_PROTOCOLS:
                result = await self._generate_custom_async(config, payload)
            elif protocol in CUSTOM_SYNC_PROTOCOLS:
                result = await self._generate_custom_sync(config, payload)
            else:
                raise RuntimeError(f"unsupported image generation protocol: {config.protocol}")
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._log_image_call(payload, config, latency_ms, "success", meta_json=result.raw_params)
            self._update_provider_health(config, "healthy", latency_ms, None)
            return result
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            self._log_image_call(payload, config, latency_ms, "failed", error=str(exc))
            self._update_provider_health(config, "degraded", latency_ms, str(exc))
            logger.warning(
                "图片生成调用失败：provider=%s protocol=%s model=%s latency_ms=%s trace_id=%s",
                config.provider,
                config.protocol,
                config.model,
                latency_ms,
                get_trace_id(),
                exc_info=True,
            )
            raise

    def _select_provider(self, provider_code: str | None = None) -> ImageProviderConfig:
        provider = None
        if provider_code:
            provider = self.db.execute(
                select(ModelProvider).where(ModelProvider.provider == provider_code, ModelProvider.is_active.is_(True))
            ).scalar_one_or_none()
            if not provider:
                raise ImageProviderUnavailable(f"ImageProvider 不存在或未启用：{provider_code}")
        else:
            providers = self.db.execute(
                select(ModelProvider)
                .where(
                    ModelProvider.is_active.is_(True),
                    or_(
                        ModelProvider.provider_type.in_(IMAGE_PROVIDER_TYPES),
                        ModelProvider.provider_type == "both",
                    ),
                )
                .order_by(ModelProvider.is_default.desc(), ModelProvider.priority.asc(), ModelProvider.display_name.asc())
            ).scalars().all()
            for item in providers:
                meta = item.meta_json or {}
                if item.provider_type in IMAGE_PROVIDER_TYPES or item.vision_model or meta.get("image_model"):
                    provider = item
                    break

        if provider:
            return self._to_config(provider)
        env_key = os.getenv("OPENAI_API_KEY") or os.getenv("IMAGE_GENERATION_API_KEY")
        if env_key:
            return ImageProviderConfig(
                id=None,
                provider="openai_image",
                display_name="OpenAI Images",
                provider_type="image_generation",
                base_url=os.getenv("OPENAI_IMAGE_BASE_URL", "https://api.openai.com/v1"),
                api_key=env_key,
                key_source="OPENAI_API_KEY" if os.getenv("OPENAI_API_KEY") else "IMAGE_GENERATION_API_KEY",
                protocol="openai_images",
                model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                cost_config={},
                meta_json={"source": "environment"},
            )
        raise ImageProviderUnavailable("ImageProvider 未配置，请先在模型网关新增 image_generation 供应商或配置 OPENAI_API_KEY。")

    def _to_config(self, provider: ModelProvider) -> ImageProviderConfig:
        api_key, key_source = self._api_key_source(provider)
        meta = provider.meta_json or {}
        raw_image_model = meta.get("image_model") or provider.vision_model
        if provider.provider_type in IMAGE_PROVIDER_TYPES:
            raw_image_model = raw_image_model or provider.chat_model
        image_model = str(raw_image_model or "").strip()
        if not image_model:
            image_model = "gpt-image-1" if provider.provider_type in IMAGE_PROVIDER_TYPES and provider.provider.startswith("openai") else ""
        return ImageProviderConfig(
            id=provider.id,
            provider=provider.provider,
            display_name=provider.display_name,
            provider_type=provider.provider_type or "image_generation",
            base_url=(provider.base_url or meta.get("base_url") or "https://api.openai.com/v1").strip(),
            api_key=api_key,
            key_source=key_source,
            protocol=provider.protocol or "openai_images",
            model=image_model,
            cost_config=provider.cost_config_json or {},
            meta_json=meta,
        )

    def _api_key_source(self, provider: ModelProvider) -> tuple[str | None, str]:
        candidates = self._ENV_KEY_CANDIDATES.get(
            provider.provider,
            (f"{provider.provider.upper()}_API_KEY", "IMAGE_GENERATION_API_KEY", "MODEL_GATEWAY_API_KEY"),
        )
        for env_name in candidates:
            value = os.getenv(env_name)
            if value:
                return value, env_name
        if provider.api_key_encrypted:
            return decrypt_secret(provider.api_key_encrypted), "database_encrypted"
        return None, "missing"

    def _log_image_call(
        self,
        payload: ImageGenerationInput,
        config: ImageProviderConfig,
        latency_ms: int,
        status: str,
        *,
        error: str | None = None,
        meta_json: dict[str, Any] | None = None,
    ) -> None:
        """记录图片生成调用日志，供网关日志与用量统计复用。"""
        try:
            course_id = self._resolve_course_id(payload.course_slug)
            cost = self._estimate_image_cost(config)
            log_meta = {
                "provider": config.provider,
                "key_source": config.key_source,
                "trace_id": get_trace_id(),
                "estimated_cost": cost["estimated_cost"],
                "currency": cost["currency"],
                "aspect_ratio": payload.aspect_ratio,
                "style_preset": payload.style_preset,
                "reference_count": len(payload.reference_paths or []),
            }
            if meta_json:
                log_meta.update(meta_json)
            self.db.add(
                ModelCallLog(
                    course_id=course_id,
                    provider_id=config.id,
                    agent_name=payload.agent_name,
                    capability="image_generation",
                    model_name=config.model,
                    request_count=1,
                    batch_count=1,
                    embedding_dim=None,
                    token_input=0,
                    token_output=0,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error[:1000] if error else None,
                    meta_json=log_meta,
                )
            )
            self.db.commit()
        except Exception:
            logger.warning(
                "写入图片生成调用日志失败：provider=%s status=%s trace_id=%s",
                config.provider,
                status,
                get_trace_id(),
                exc_info=True,
            )
            self.db.rollback()

    def _update_provider_health(
        self,
        config: ImageProviderConfig,
        status: str,
        latency_ms: int,
        error: str | None,
    ) -> None:
        """同步图片供应商健康状态。"""
        if not config.id:
            return
        try:
            provider = self.db.get(ModelProvider, config.id)
            if not provider:
                return
            next_status = status if status in {"healthy", "degraded", "down", "standby", "unhealthy"} else provider.health_status
            provider.last_checked_at = datetime.now(timezone.utc)
            health = self.db.execute(select(ModelProviderHealth).where(ModelProviderHealth.provider_id == config.id)).scalar_one_or_none()
            if not health:
                health = ModelProviderHealth(provider_id=config.id, status=next_status, success_rate=1.0, avg_latency_ms=0, consecutive_failures=0)
                self.db.add(health)
                self.db.flush()
            health.avg_latency_ms = latency_ms
            health.last_error = error[:1000] if error else None
            health.consecutive_failures = 0 if not error else health.consecutive_failures + 1
            if error and health.consecutive_failures >= settings.MODEL_GATEWAY_FAILURE_THRESHOLD:
                next_status = "down"
            health.status = next_status
            health.success_rate = 0.98 if not error else max(0.1, health.success_rate - 0.05)
            provider.health_status = next_status
            self.db.commit()
        except Exception:
            logger.warning(
                "更新图片生成供应商健康状态失败：provider=%s status=%s trace_id=%s",
                config.provider,
                status,
                get_trace_id(),
                exc_info=True,
            )
            self.db.rollback()

    def _resolve_course_id(self, course_slug: str | None) -> uuid.UUID | None:
        if not course_slug:
            return None
        course = self.db.execute(
            select(Course).where(or_(Course.slug == course_slug, Course.id == self._safe_uuid_text(course_slug)))
        ).scalar_one_or_none()
        return course.id if course else None

    @staticmethod
    def _estimate_image_cost(config: ImageProviderConfig) -> dict[str, Any]:
        cost_config = config.cost_config or {}
        currency = str(cost_config.get("currency") or "CNY")
        unit_price = float(cost_config.get("image_unit_price") or cost_config.get("unit_price") or 0)
        return {"currency": currency, "estimated_cost": round(unit_price, 6)}

    @staticmethod
    def _safe_uuid_text(value: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            return "00000000-0000-0000-0000-000000000000"

    async def _generate_openai_compatible(self, config: ImageProviderConfig, payload: ImageGenerationInput) -> GeneratedImage:
        request_body: dict[str, Any] = {
            "model": config.model,
            "prompt": payload.prompt,
            "n": 1,
            "size": resolve_image_size(payload.aspect_ratio),
            "response_format": config.meta_json.get("response_format", "b64_json"),
        }
        request_body.update(config.meta_json.get("default_params") or {})
        request_body.update(payload.extra_params or {})
        request_body = {key: value for key, value in request_body.items() if value is not None}
        headers = {"Authorization": _bearer_auth_header(config.api_key or ""), "Content-Type": "application/json"}
        started = time.perf_counter()
        async with httpx.AsyncClient(**model_gateway_client_kwargs(config.base_url, settings.RESOURCE_IMAGE_GENERATION_TIMEOUT_SECONDS)) as client:
            response = await client.post(_image_generations_url(config.base_url), headers=headers, json=request_body)
            response.raise_for_status()
            data = response.json()
        latency_ms = int((time.perf_counter() - started) * 1000)
        item = (data.get("data") or [{}])[0] if isinstance(data, dict) else {}
        image_bytes = None
        if isinstance(item, dict) and item.get("b64_json"):
            image_bytes = base64.b64decode(str(item["b64_json"]))
        width, height, mime_type = detect_image_size(image_bytes or b"")
        return GeneratedImage(
            url=str(item.get("url")) if isinstance(item, dict) and item.get("url") else None,
            bytes_data=image_bytes,
            width=width,
            height=height,
            mime_type=mime_type,
            provider=config.provider,
            model=config.model,
            prompt=payload.prompt,
            revised_prompt=str(item.get("revised_prompt")) if isinstance(item, dict) and item.get("revised_prompt") else None,
            raw_params={
                "protocol": config.protocol,
                "request": self._safe_request_params(request_body),
                "response_meta": self._safe_response_meta(data),
                "latency_ms": latency_ms,
                "key_source": config.key_source,
            },
        )

    async def _generate_fal_queue(self, config: ImageProviderConfig, payload: ImageGenerationInput) -> GeneratedImage:
        model_path = str(config.meta_json.get("endpoint_path") or config.model).strip().strip("/")
        endpoint = config.base_url.rstrip("/")
        if not endpoint.endswith(model_path):
            endpoint = f"{endpoint}/{model_path}"
        request_body = {
            "prompt": payload.prompt,
            "image_size": config.meta_json.get("image_size") or payload.aspect_ratio,
            "num_images": 1,
            **(config.meta_json.get("default_params") or {}),
            **(payload.extra_params or {}),
        }
        if payload.reference_paths:
            request_body["reference_images"] = payload.reference_paths
        headers = {"Authorization": _bearer_auth_header(config.api_key or ""), "Content-Type": "application/json"}
        async with httpx.AsyncClient(**model_gateway_client_kwargs(config.base_url, settings.RESOURCE_IMAGE_GENERATION_TIMEOUT_SECONDS)) as client:
            response = await client.post(endpoint, headers=headers, json=request_body)
            response.raise_for_status()
            queued = response.json()
            result_payload = await self._poll_fal_result(client, queued, headers)
        return self._image_from_payload(config, payload, result_payload, {"protocol": config.protocol, "request": self._safe_request_params(request_body), "queue": queued})

    async def _poll_fal_result(self, client: httpx.AsyncClient, queued: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        status_url = queued.get("status_url")
        response_url = queued.get("response_url")
        if not status_url and not response_url:
            return queued
        for _attempt in range(settings.RESOURCE_IMAGE_GENERATION_POLL_ATTEMPTS):
            if status_url:
                status_response = await client.get(str(status_url), headers=headers)
                status_response.raise_for_status()
                status_payload = status_response.json()
                status_value = str(status_payload.get("status") or status_payload.get("state") or "").upper()
                if status_value in {"COMPLETED", "SUCCEEDED", "SUCCESS"}:
                    response_url = status_payload.get("response_url") or response_url
                    if not response_url:
                        return status_payload
                    break
                if status_value in {"FAILED", "ERROR", "CANCELLED"}:
                    raise RuntimeError(f"fal.ai image generation failed: {status_payload}")
            await asyncio.sleep(settings.RESOURCE_IMAGE_GENERATION_POLL_INTERVAL_SECONDS)
        if response_url:
            result_response = await client.get(str(response_url), headers=headers)
            result_response.raise_for_status()
            return result_response.json()
        raise TimeoutError("fal.ai image generation timed out")

    async def _generate_custom_sync(self, config: ImageProviderConfig, payload: ImageGenerationInput) -> GeneratedImage:
        request_body = self._custom_request_body(config, payload)
        headers = {"Authorization": _bearer_auth_header(config.api_key or ""), "Content-Type": "application/json"}
        async with httpx.AsyncClient(**model_gateway_client_kwargs(config.base_url, settings.RESOURCE_IMAGE_GENERATION_TIMEOUT_SECONDS)) as client:
            response = await client.post(config.base_url, headers=headers, json=request_body)
            response.raise_for_status()
            data = response.json()
        return self._image_from_payload(config, payload, data, {"protocol": config.protocol, "request": self._safe_request_params(request_body)})

    async def _generate_custom_async(self, config: ImageProviderConfig, payload: ImageGenerationInput) -> GeneratedImage:
        request_body = self._custom_request_body(config, payload)
        headers = {"Authorization": _bearer_auth_header(config.api_key or ""), "Content-Type": "application/json"}
        async with httpx.AsyncClient(**model_gateway_client_kwargs(config.base_url, settings.RESOURCE_IMAGE_GENERATION_TIMEOUT_SECONDS)) as client:
            response = await client.post(config.base_url, headers=headers, json=request_body)
            response.raise_for_status()
            queued = response.json()
            result = await self._poll_custom_result(client, config, queued, headers)
        return self._image_from_payload(config, payload, result, {"protocol": config.protocol, "request": self._safe_request_params(request_body), "queue": queued})

    def _custom_request_body(self, config: ImageProviderConfig, payload: ImageGenerationInput) -> dict[str, Any]:
        body = {
            "model": config.model,
            "prompt": payload.prompt,
            "aspect_ratio": payload.aspect_ratio,
            "style_preset": payload.style_preset,
            "reference_images": payload.reference_paths or [],
        }
        body.update(config.meta_json.get("default_params") or {})
        body.update(payload.extra_params or {})
        return body

    async def _poll_custom_result(
        self,
        client: httpx.AsyncClient,
        config: ImageProviderConfig,
        queued: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        meta = config.meta_json
        status_url = _extract_json_path(queued, str(meta.get("status_url_path") or "status_url"))
        result_url = _extract_json_path(queued, str(meta.get("result_url_path") or "result_url")) or _extract_json_path(queued, "response_url")
        poll_template = meta.get("poll_url_template")
        request_id = _extract_json_path(queued, str(meta.get("request_id_path") or "request_id"))
        if not status_url and poll_template and request_id:
            status_url = str(poll_template).format(request_id=request_id)
        if not status_url and result_url:
            status_url = result_url
        if not status_url:
            return queued
        for _attempt in range(settings.RESOURCE_IMAGE_GENERATION_POLL_ATTEMPTS):
            response = await client.get(str(status_url), headers=headers)
            response.raise_for_status()
            data = response.json()
            status_value = str(_extract_json_path(data, str(meta.get("status_path") or "status")) or "").lower()
            if status_value in {"completed", "succeeded", "success", "done"}:
                return data
            if status_value in {"failed", "error", "cancelled"}:
                raise RuntimeError(f"custom image generation failed: {data}")
            await asyncio.sleep(settings.RESOURCE_IMAGE_GENERATION_POLL_INTERVAL_SECONDS)
        raise TimeoutError("custom image generation timed out")

    def _image_from_payload(
        self,
        config: ImageProviderConfig,
        request: ImageGenerationInput,
        payload: dict[str, Any],
        raw_params: dict[str, Any],
    ) -> GeneratedImage:
        meta = config.meta_json
        url = (
            _extract_json_path(payload, str(meta.get("image_url_path") or "images.0.url"))
            or _extract_json_path(payload, "data.0.url")
            or payload.get("url")
            or payload.get("image_url")
        )
        b64_value = (
            _extract_json_path(payload, str(meta.get("b64_json_path") or "images.0.b64_json"))
            or _extract_json_path(payload, "data.0.b64_json")
            or payload.get("b64_json")
        )
        bytes_data = base64.b64decode(str(b64_value)) if b64_value else None
        width = _extract_json_path(payload, str(meta.get("width_path") or "images.0.width"))
        height = _extract_json_path(payload, str(meta.get("height_path") or "images.0.height"))
        detected_width, detected_height, detected_mime = detect_image_size(bytes_data or b"")
        revised_prompt = (
            _extract_json_path(payload, str(meta.get("revised_prompt_path") or "images.0.revised_prompt"))
            or _extract_json_path(payload, "data.0.revised_prompt")
        )
        return GeneratedImage(
            url=str(url) if url else None,
            bytes_data=bytes_data,
            width=int(width) if isinstance(width, (int, float)) else detected_width,
            height=int(height) if isinstance(height, (int, float)) else detected_height,
            mime_type=detected_mime,
            provider=config.provider,
            model=config.model,
            prompt=request.prompt,
            revised_prompt=str(revised_prompt) if revised_prompt else None,
            raw_params={**raw_params, "response_meta": self._safe_response_meta(payload), "key_source": config.key_source},
        )

    @staticmethod
    def _safe_request_params(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key.lower() not in {"api_key", "key", "token"}}

    @staticmethod
    def _safe_response_meta(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        safe = {key: value for key, value in payload.items() if key not in {"data", "images"}}
        if "data" in payload and isinstance(payload["data"], list):
            safe["data_count"] = len(payload["data"])
        if "images" in payload and isinstance(payload["images"], list):
            safe["image_count"] = len(payload["images"])
        return safe


async def download_image_bytes(url: str) -> tuple[bytes, str]:
    """下载供应商返回的远程图片，用于落入本地对象存储。"""
    async with httpx.AsyncClient(**model_gateway_client_kwargs(url, settings.RESOURCE_IMAGE_GENERATION_TIMEOUT_SECONDS)) as client:
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type") or "image/png"
        return response.content, content_type.split(";", 1)[0]


def safe_image_suffix(mime_type: str | None) -> str:
    """根据 MIME 类型选择安全文件扩展名。"""
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mapping.get((mime_type or "").lower(), ".png")


def normalize_asset_title(value: str) -> str:
    """限制资产标题长度，避免异常文件名进入展示层。"""
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:120] or "教学图解"


def storage_relative_path(*parts: str) -> str:
    """拼接对象存储相对路径。"""
    return str(Path("resource-assets", *parts)).replace("\\", "/")
