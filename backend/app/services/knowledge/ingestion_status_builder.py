from __future__ import annotations

from typing import Any


def build_ingestion_stage(
    name: str,
    step_index: int,
    *,
    pipeline_index: int,
    processing: bool,
    failed: bool,
    meta_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造单个知识库入库阶段的展示状态。"""
    if failed and step_index > pipeline_index:
        status = "failed" if step_index == pipeline_index + 1 else "queued"
    elif pipeline_index >= step_index:
        status = "completed"
    elif pipeline_index + 1 == step_index and processing:
        status = "running"
    else:
        status = "queued"
    return {
        "name": name,
        "status": status,
        "progress": 100 if status == "completed" else 60 if status == "running" else 0,
        "meta": meta_json or {},
    }


def build_ingestion_stages(
    *,
    file_status: str | None,
    ready: bool,
    processing: bool,
    failed: bool,
) -> list[dict[str, Any]]:
    """根据 ChatDoc 文件状态构造完整入库流水线阶段。"""
    # 延迟导入可避免 KnowledgeRepository 与 iflytek 包在初始化阶段互相依赖。
    from app.services.knowledge.iflytek.status_labels import chatdoc_pipeline_step_index

    pipeline_index = chatdoc_pipeline_step_index(
        file_status if file_status else ("vectored" if ready else "uploaded")
    )
    stage_meta = {"file_status": file_status}
    return [
        build_ingestion_stage("chatdoc_upload", 0, pipeline_index=pipeline_index, processing=processing, failed=failed, meta_json=stage_meta),
        build_ingestion_stage("chatdoc_parse", 1, pipeline_index=pipeline_index, processing=processing, failed=failed, meta_json=stage_meta),
        build_ingestion_stage("chatdoc_split", 2, pipeline_index=pipeline_index, processing=processing, failed=failed, meta_json=stage_meta),
        build_ingestion_stage("chatdoc_embed", 3, pipeline_index=pipeline_index, processing=processing, failed=failed, meta_json=stage_meta),
        build_ingestion_stage("chatdoc_ready", 4, pipeline_index=pipeline_index, processing=processing, failed=failed, meta_json=stage_meta),
    ]


def compute_ingestion_progress(
    *,
    ready: bool,
    awaiting: bool,
    processing: bool,
    failed: bool,
) -> int:
    """计算知识库入库进度，避免轮询失败时展示误导性固定百分比。"""
    if ready:
        return 100
    if awaiting:
        return 85
    if processing:
        return 70
    if failed:
        return 0
    return 20


def resolve_chatdoc_file_status(meta: dict[str, Any]) -> str | None:
    """从文档元数据中解析标准化 ChatDoc 文件状态。"""
    from app.services.knowledge.iflytek.status_labels import normalize_chatdoc_file_status

    chatdoc_status = meta.get("chatdoc_status") or {}
    return normalize_chatdoc_file_status(
        meta.get("chatdoc_file_status")
        or chatdoc_status.get("fileStatus")
        or chatdoc_status.get("file_status")
    )


def ingestion_flags(parse_status: str, vector_status: str, file_status: str | None) -> tuple[bool, bool, bool, bool]:
    """根据解析状态、向量状态和云端文件状态推导入库布尔标记。"""
    from app.services.knowledge.iflytek.cloud_status import is_awaiting_activation

    failed = parse_status == "failed" or vector_status == "failed"
    ready = vector_status == "ready"
    awaiting = is_awaiting_activation(vector_status, file_status)
    processing = (
        vector_status in {"processing", "pending", "pending_review"}
        or parse_status == "processing"
    ) and not awaiting
    return failed, ready, awaiting, processing
