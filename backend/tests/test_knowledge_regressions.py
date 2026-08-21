"""知识库仓储、种子同步和本地检索的聚焦回归测试。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.config import settings
from app.services.knowledge import local_knowledge
from app.services.knowledge.local_knowledge import LocalKnowledgeService
from app.services.knowledge.repository import KnowledgeRepository
from scripts.seed_curriculum_catalog import _sync_concept, _sync_prerequisite


def test_courses_with_knowledge_returns_uuids_for_admin(monkeypatch) -> None:
    """管理员应绕过选课过滤，并把课程主键规范化为字符串。"""
    monkeypatch.setattr(settings, "RAG_BACKEND", "iflytek_chatdoc")
    db = MagicMock()
    course_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role_code="admin")

    db.execute.return_value.scalar_one_or_none.return_value = user
    db.execute.return_value.scalars.return_value.all.return_value = [course_id]

    result = KnowledgeRepository(db).get_courses_with_knowledge("admin-external-id")

    assert result == {"course_ids": [str(course_id)]}
    final_statement = str(db.execute.call_args_list[-1].args[0])
    assert "course_memberships" not in final_statement


def test_courses_with_knowledge_filters_students_by_active_membership(monkeypatch) -> None:
    """普通学生只能看到自己有效选课范围内的已就绪课程。"""
    monkeypatch.setattr(settings, "RAG_BACKEND", "iflytek_chatdoc")
    db = MagicMock()
    user = SimpleNamespace(id=uuid.uuid4(), role_code="student")

    db.execute.return_value.scalar_one_or_none.return_value = user
    db.execute.return_value.scalars.return_value.all.return_value = [uuid.uuid4()]

    result = KnowledgeRepository(db).get_courses_with_knowledge("student-external-id")

    assert len(result["course_ids"]) == 1
    final_statement = str(db.execute.call_args_list[-1].args[0])
    assert "course_memberships" in final_statement


def test_courses_with_knowledge_returns_empty_for_unknown_user() -> None:
    """不存在的用户不应获得任何课程列表。"""
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    result = KnowledgeRepository(db).get_courses_with_knowledge("missing-user")

    assert result == {"course_ids": []}
    assert db.execute.call_count == 1


def test_seed_sync_concept_flushes_new_concept_before_prerequisite(monkeypatch) -> None:
    """新知识点必须先 flush 获得主键，再建立先修关系，避免空外键。"""
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    def assign_id_on_flush() -> None:
        added = db.add.call_args_list[-1].args[0]
        added.id = uuid.uuid4()

    db.flush.side_effect = assign_id_on_flush
    course = SimpleNamespace(id=uuid.uuid4())
    section = SimpleNamespace(id=uuid.uuid4())
    resource = {
        "id": "python-foundations",
        "title": "Python 基础",
        "description": "语言基础",
        "difficulty": "basic",
    }

    concept = _sync_concept(db, course, section, resource, 1)
    prerequisite = SimpleNamespace(id=uuid.uuid4())
    _sync_prerequisite(db, course, concept, prerequisite)

    db.flush.assert_called_once()
    added_relation = db.add.call_args_list[-1].args[0]
    assert added_relation.concept_id == concept.id


def test_local_readiness_uses_document_and_chunk_counts(monkeypatch) -> None:
    """本地课程就绪状态必须同时要求文档数与可检索向量切片数大于零。"""
    db = MagicMock()
    course = SimpleNamespace(id=uuid.uuid4(), slug="data_system", title="数据与系统设计")
    monkeypatch.setattr(LocalKnowledgeService, "_course", lambda _self, _course_id: course)
    db.scalar.side_effect = [3, 42]

    result = LocalKnowledgeService(db).readiness("data_system")

    assert result == {
        "course_id": "data_system",
        "course_title": "数据与系统设计",
        "ready": True,
        "document_count": 3,
        "chunk_count": 42,
    }


def test_local_search_returns_citation_from_vector_candidate(monkeypatch) -> None:
    """向量候选应转换为统一 Citation，空 BM25 候选不影响混合检索返回。"""
    db = MagicMock()
    course = SimpleNamespace(id=uuid.uuid4(), slug="data_system", title="数据与系统设计")
    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        page_no=3,
        chunk_index=7,
        content="高可用系统通常依赖冗余、限流、熔断和降级策略。",
        section_path=None,
        heading_path=[],
    )
    document = SimpleNamespace(id=uuid.uuid4(), title="高可用设计", deleted_at=None)
    monkeypatch.setattr(LocalKnowledgeService, "_course", lambda _self, _course_id: course)
    monkeypatch.setattr(
        local_knowledge.local_embedding_service,
        "encode",
        lambda _texts: [[0.1, 0.2]],
    )
    db.execute.return_value.all.return_value = [(chunk, document, 0.2)]
    monkeypatch.setitem(
        local_knowledge._bm25_cache,
        str(course.id),
        SimpleNamespace(
            bm25=SimpleNamespace(get_scores=lambda _tokens: []),
            chunk_ids=[],
            chunk_map={},
            doc_map={},
        ),
    )

    results = LocalKnowledgeService(db).search("data_system", "高可用系统", limit=3)

    assert len(results) == 1
    citation = results[0]
    assert citation.source_title == "高可用设计"
    assert citation.page_no == 3
    assert citation.provenance_source == "local_pgvector"
    assert citation.similarity == round(settings.LOCAL_KNOWLEDGE_VECTOR_WEIGHT * 0.8, 4)
