from __future__ import annotations

import json
import logging
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tracing import get_trace_id
from app.services.agent.retrieval_guard import max_citation_score, should_refuse_low_confidence
from app.schemas.common import Citation
from app.services.knowledge.backend import get_retrieval_backend

logger = logging.getLogger(__name__)


class CourseRetriever:
    """课程知识库检索服务，负责获取引用切片并记录查询指标。"""

    async def retrieve(
        self,
        db: Session,
        course_id: str,
        query: str,
        concept_id: str | None = None,
        document_id: str | None = None,
    ) -> list[Citation]:
        """从当前课程知识库检索可引用切片。

        当 ``RAG_BACKEND=iflytek_chatdoc`` 时使用讯飞 ChatDoc ``vector/search``。
        运维监控迁移存在时，每次检索都会记录到 ``rag_query_logs``。
        """
        started_at = time.perf_counter()
        citations = await get_retrieval_backend(db).search(course_id, query, concept_id, document_id=document_id)
        latency_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        self._log_query(
            db=db,
            course_slug=course_id,
            concept_code=concept_id,
            query=query,
            citations=citations,
            latency_ms=latency_ms,
        )
        return citations

    @staticmethod
    def _log_query(
        db: Session,
        course_slug: str,
        concept_code: str | None,
        query: str,
        citations: list[Citation],
        *,
        latency_ms: int = 0,
    ) -> None:
        """记录 RAG 查询命中、置信度和拒答指标，失败时不影响检索主流程。"""
        top_score = max_citation_score(citations)
        threshold = settings.RAG_RETRIEVAL_MIN_SCORE
        refused, _ = should_refuse_low_confidence(citations, require_citations=True, threshold=threshold)
        hit = bool(citations) and top_score >= threshold and not refused
        # concept_code 为空时用显式 NULL 条件，避免 PostgreSQL 无法推断 $N 参数类型
        # （AmbiguousParameter）而失败，进而 rollback 掉同事务里刚创建的会话记录。
        concept_join = (
            "LEFT JOIN course_concepts cc ON cc.course_id = c.id AND cc.code = :concept_code"
            if concept_code
            else "LEFT JOIN course_concepts cc ON cc.course_id = c.id AND FALSE"
        )
        try:
            db.execute(
                text(
                    f"""
                    INSERT INTO rag_query_logs (
                        id, course_id, concept_id, intent, query_text, hit, top_score,
                        citation_count, refused, latency_ms, retrieval_scope, meta_json
                    )
                    SELECT gen_random_uuid(), c.id, cc.id, 'course_qa', :query_text, :hit,
                           :top_score, :citation_count, :refused, :latency_ms, 'course',
                           CAST(:meta_json AS JSONB)
                    FROM courses c
                    {concept_join}
                    WHERE c.slug = :course_slug
                    LIMIT 1
                    """
                ),
                {
                    "course_slug": course_slug,
                    "concept_code": concept_code,
                    "query_text": query[:2000],
                    "hit": hit,
                    "top_score": top_score,
                    "citation_count": len(citations),
                    "refused": refused,
                    "latency_ms": latency_ms,
                    "meta_json": json.dumps(
                        {
                            "source": "runtime_retriever",
                            "trace_id": get_trace_id(),
                            "threshold": threshold,
                            "refusal_reason": "low_confidence" if refused and citations else ("no_hit" if not citations else None),
                        }
                    ),
                },
            )
            db.commit()
        except Exception:
            # 指标记录不能影响学习主流程；缺少迁移或本地 SQLite 冒烟测试时可以跳过该运维日志。
            logger.debug(
                "写入 RAG 查询日志失败，将不影响检索结果返回：course_slug=%s concept_code=%s trace_id=%s",
                course_slug,
                concept_code,
                get_trace_id(),
                exc_info=True,
            )
            db.rollback()
