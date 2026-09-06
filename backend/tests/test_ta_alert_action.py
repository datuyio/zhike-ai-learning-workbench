"""Wave 2 纯函数单测：预警干预动作归一化 + 通知文案构造（无 DB）。"""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.v1.routes.ta.alerts import _build_alert_notification, _dispatch_intervention
from app.api.v1.routes.ta_student import _build_notification_dict

ALERT_TITLE = "李华 掌握度预警：卷积神经网络"
ALERT_DESC = "李华 在知识点《卷积神经网络》的平均掌握度仅 45%，低于 60% 预警阈值。"


def test_build_alert_notification_prefers_content() -> None:
    n = _build_alert_notification(ALERT_TITLE, ALERT_DESC, "请今晚前完成卷积练习")
    assert n["title"] == f"学习提醒：{ALERT_TITLE}"
    assert n["body"] == "请今晚前完成卷积练习"


def test_build_alert_notification_falls_back_to_description() -> None:
    n = _build_alert_notification(ALERT_TITLE, ALERT_DESC, None)
    assert n["body"] == ALERT_DESC


def test_build_alert_notification_default_when_empty() -> None:
    n = _build_alert_notification(ALERT_TITLE, None, None)
    assert n["body"] == "助教关注到你的学习情况，请及时查看。"


def test_dispatch_notify_returns_notification() -> None:
    r = _dispatch_intervention("notify", ALERT_TITLE, ALERT_DESC, "请尽快查看", None, None)
    assert r["action_type"] == "notify"
    assert r["notification"] == {"title": f"学习提醒：{ALERT_TITLE}", "body": "请尽快查看"}


def test_dispatch_recommend_keeps_resource_ids() -> None:
    r = _dispatch_intervention("recommend_resources", ALERT_TITLE, ALERT_DESC, None, ["r1", "r2"], None)
    assert r["action_type"] == "recommend_resources"
    assert r["resource_ids"] == ["r1", "r2"]
    assert r["notification"] is None


def test_dispatch_book_tutoring_keeps_time() -> None:
    t = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
    r = _dispatch_intervention("book_tutoring", ALERT_TITLE, ALERT_DESC, None, None, t)
    assert r["tutoring_time"] == t
    assert r["notification"] is None


def test_dispatch_note_only() -> None:
    r = _dispatch_intervention("note", ALERT_TITLE, ALERT_DESC, "已电话联系家长", None, None)
    assert r["action_type"] == "note"
    assert r["notification"] is None


def test_dispatch_invalid_action_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        _dispatch_intervention("hack", ALERT_TITLE, ALERT_DESC, None, None, None)


def test_build_notification_dict_shape() -> None:
    n = SimpleNamespace(
        id="abc", title="新作业：卷积", body="已发布",
        notification_type="assignment", source_type="assignment", source_id="q1",
        is_read=False,
        created_at=datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc),
    )
    d = _build_notification_dict(n)
    assert d["id"] == "abc"
    assert d["title"] == "新作业：卷积"
    assert d["notification_type"] == "assignment"
    assert d["is_read"] is False
    assert d["created_at"] == "2026-08-07T09:00:00+00:00"
