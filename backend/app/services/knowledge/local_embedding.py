from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Sequence

import numpy as np

from app.core.config import settings


class LocalEmbeddingError(RuntimeError):
    """本地 Embedding 初始化或编码失败。"""


class LocalEmbeddingService:
    """惰性加载本地中文 Embedding 模型，避免导入应用时触发模型下载。"""

    @cached_property
    def model(self):
        """首次真正编码时加载模型；模型缺失时由 Sentence Transformers 执行一次下载。"""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise LocalEmbeddingError("本地知识库需要安装 sentence-transformers；当前仅云端 ChatDoc 配置可直接运行。") from exc
        cache_dir = Path(settings.LOCAL_EMBEDDING_CACHE_DIR).expanduser()
        cache_dir.mkdir(parents=True, exist_ok=True)
        has_cached_weights = any(cache_dir.rglob("*.safetensors"))
        try:
            return SentenceTransformer(
                settings.LOCAL_EMBEDDING_MODEL,
                cache_folder=str(cache_dir),
                device=settings.LOCAL_EMBEDDING_DEVICE,
                local_files_only=has_cached_weights,
            )
        except Exception as exc:
            raise LocalEmbeddingError(f"无法加载本地 Embedding 模型 {settings.LOCAL_EMBEDDING_MODEL}，请检查网络、模型缓存目录和磁盘空间：{exc}") from exc

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """批量生成归一化向量，并校验维度与配置一致。"""
        if not texts:
            return []
        try:
            vectors = self.model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        except Exception as exc:
            raise LocalEmbeddingError(f"本地 Embedding 编码失败：{exc}") from exc
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.shape[1] != settings.LOCAL_EMBEDDING_DIMENSION:
            raise LocalEmbeddingError(f"模型输出维度为 {array.shape[1]}，但配置要求 {settings.LOCAL_EMBEDDING_DIMENSION}；请同步调整模型和数据库 vector 维度。")
        return array.tolist()


local_embedding_service = LocalEmbeddingService()
