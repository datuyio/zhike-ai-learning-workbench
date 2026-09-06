"""助教公告纯逻辑单元测试：多班级目标归一化与去重。"""
from app.api.v1.routes.ta.announcements import AnnouncementCreateRequest, _normalize_announcement_class_ids


def test_normalize_announcement_class_ids_multi_dedup() -> None:
    payload = AnnouncementCreateRequest(title="t", body="b", class_ids=["c1", "c2", "c1"])
    assert _normalize_announcement_class_ids(payload) == ["c1", "c2"]


def test_normalize_announcement_class_ids_filters_empty() -> None:
    payload = AnnouncementCreateRequest(title="t", body="b", class_ids=["", "c1", ""])
    assert _normalize_announcement_class_ids(payload) == ["c1"]


def test_normalize_announcement_class_ids_falls_back_to_single() -> None:
    payload = AnnouncementCreateRequest(title="t", body="b", class_ids=None, class_id="c9")
    assert _normalize_announcement_class_ids(payload) == ["c9"]


def test_normalize_announcement_class_ids_empty_means_all() -> None:
    payload = AnnouncementCreateRequest(title="t", body="b")
    assert _normalize_announcement_class_ids(payload) == []
