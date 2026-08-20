from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.common import Citation
from app.services.knowledge.iflytek.retrieval_adapter import IflytekRetrievalAdapter
from app.services.knowledge.local_knowledge import LocalKnowledgeService


class RetrievalBackend(Protocol):
    """知识检索后端协议。

    用途:
        约束不同 RAG 后端必须提供统一的异步检索入口。

    副作用/失败:
        协议本身不执行逻辑；具体实现可能访问数据库或外部检索服务，并抛出实现层异常。
    """

    async def search(
        self,
        course_slug: str,
        query: str,
        concept_id: str | None = None,
        limit: int | None = None,
        document_id: str | None = None,
    ) -> list[Citation]:
        """按课程和查询文本检索引用片段。

        参数:
            course_slug: 课程 slug，用于限定检索范围。
            query: 用户查询或待检索文本。
            concept_id: 可选知识点标识，用于进一步过滤检索范围。
            limit: 可选返回数量上限，由实现自行裁剪。
            document_id: 可选文档 ID，用于限定单个文档内检索。

        返回:
            Citation 列表，按实现层相关性排序。

        副作用/失败:
            具体实现可能访问外部服务、数据库或本地索引；失败时按实现层异常向上抛出。
        """
        ...


class LocalPgVectorRetrievalBackend:
    """基于本地切片和 pgvector 的检索后端。"""

    def __init__(self, db: Session) -> None:
        self.service = LocalKnowledgeService(db)

    async def search(self, course_slug: str, query: str, concept_id: str | None = None, limit: int | None = None, document_id: str | None = None) -> list[Citation]:
        _ = concept_id
        return self.service.search(course_slug, query, limit or settings.RAG_RETRIEVAL_LIMIT, document_id)


class IflytekChatDocRetrievalBackend:
    """基于讯飞 ChatDoc 的知识检索后端。

    用途:
        将统一检索协议适配到 IflytekRetrievalAdapter，隐藏云端 ChatDoc 检索细节。

    副作用/失败:
        调用检索方法时会访问数据库和讯飞 ChatDoc 相关服务；配置、网络或供应商错误会向上抛出。
    """

    def __init__(self, db: Session) -> None:
        """初始化检索后端。

        参数:
            db: SQLAlchemy 会话，用于读取课程、文档和检索元数据。

        返回:
            None。

        副作用/失败:
            创建 IflytekRetrievalAdapter 实例；不主动发起网络请求。
        """
        self.adapter = IflytekRetrievalAdapter(db)

    async def search(
        self,
        course_slug: str,
        query: str,
        concept_id: str | None = None,
        limit: int | None = None,
        document_id: str | None = None,
    ) -> list[Citation]:
        """调用讯飞 ChatDoc 适配器执行检索。

        参数:
            course_slug: 课程 slug，用于定位课程文档集合。
            query: 检索文本。
            concept_id: 可选知识点标识，用于概念过滤。
            limit: 可选返回数量上限。
            document_id: 可选文档 ID，用于限定检索文档。

        返回:
            Citation 列表；适配器返回的元信息在此处丢弃。

        副作用/失败:
            可能访问数据库和讯飞 ChatDoc 服务；检索失败、配置缺失或供应商异常会向上抛出。
        """
        citations, _meta = await self.adapter.search(course_slug, query, concept_id, limit, document_id)
        return citations


def get_retrieval_backend(db: Session) -> RetrievalBackend:
    """根据当前配置创建知识检索后端。

    参数:
        db: SQLAlchemy 会话，用于传入具体检索后端。

    返回:
        符合 RetrievalBackend 协议的检索后端实例。

    副作用/失败:
        当 RAG_BACKEND 不是 iflytek_chatdoc 时抛出 RuntimeError；创建实例本身不发起检索请求。
    """
    if settings.RAG_BACKEND == "local_pgvector":
        return LocalPgVectorRetrievalBackend(db)
    if settings.RAG_BACKEND == "iflytek_chatdoc":
        return IflytekChatDocRetrievalBackend(db)
    raise RuntimeError(f"不支持的 RAG_BACKEND：{settings.RAG_BACKEND}")
