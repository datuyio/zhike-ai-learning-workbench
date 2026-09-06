"""助教端纯逻辑单元测试：批改 JSON 解析防御链 + 相对时间格式化 + 分数钳制 + SSE 编码 + 模板/限流 + 统计。"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.rate_limit import consume_fixed_window
from app.api.v1.routes.ta._shared import _relative_time, _render_template, _sse_payload
from app.api.v1.routes.ta.grading import (
    _clamp_score,
    _compute_grading_stats,
    _parse_grading_json,
    _score_bucket,
)


def test_parse_grading_json_strict() -> None:
    raw = '{"score": 85, "comment": "掌握较好", "issues": ["步骤不完整"]}'
    parsed = _parse_grading_json(raw)
    assert parsed["score"] == 85.0
    assert parsed["comment"] == "掌握较好"
    assert parsed["issues"] == ["步骤不完整"]


def test_parse_grading_json_markdown_wrapped() -> None:
    raw = '```json\n{"score": 70, "comment": "需加强", "issues": []}\n```'
    parsed = _parse_grading_json(raw)
    assert parsed["score"] == 70.0


def test_parse_grading_json_invalid() -> None:
    assert _parse_grading_json("无法解析的内容") is None
    assert _parse_grading_json('{"score": "abc"}') is None
    assert _parse_grading_json('{"comment": "没有分数"}') is None
    assert _parse_grading_json('{"score": true}') is None


def test_relative_time_just_now() -> None:
    dt = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert _relative_time(dt) == "刚刚"


def test_relative_time_minutes() -> None:
    dt = datetime.now(timezone.utc) - timedelta(minutes=5, seconds=10)
    assert _relative_time(dt) == "5 分钟前"


def test_relative_time_hours() -> None:
    dt = datetime.now(timezone.utc) - timedelta(hours=3, minutes=5)
    assert _relative_time(dt) == "3 小时前"


def test_relative_time_days() -> None:
    dt = datetime.now(timezone.utc) - timedelta(days=2, hours=1)
    assert _relative_time(dt) == "2 天前"


def test_relative_time_none() -> None:
    assert _relative_time(None) == "未知时间"


def test_clamp_score_upper_bound() -> None:
    assert _clamp_score(120, 100) == 100.0


def test_clamp_score_lower_bound() -> None:
    assert _clamp_score(-5, 100) == 0.0


def test_clamp_score_within_range() -> None:
    assert _clamp_score(88.5, 100) == 88.5


def test_sse_payload_frame_format() -> None:
    payload = _sse_payload({"type": "delta", "content": "你好"})
    assert payload.startswith("data: ")
    assert payload.endswith("\n\n")
    assert '"type": "delta"' in payload
    assert '"content": "你好"' in payload


def test_sse_payload_serializes_uuid_with_default() -> None:
    import uuid

    payload = _sse_payload({"id": uuid.UUID(int=1), "type": "done"})
    assert payload.startswith("data: ")
    assert "00000000-0000-0000-0000-000000000001" in payload


def test_render_template_substitutes_all_placeholders() -> None:
    template = "{student_name} 在《{concept}》掌握度 {mastery}%"
    text = _render_template(template, {"student_name": "张三", "concept": "导数", "mastery": 55})
    assert text == "张三 在《导数》掌握度 55%"


def test_render_template_missing_variable_removed() -> None:
    template = "{student_name} {absent} 预警"
    text = _render_template(template, {"student_name": "李四"})
    assert text == "李四  预警"
    assert "{" not in text


def test_render_template_none_value_empty() -> None:
    text = _render_template("{name} 分 {delta} 分", {"name": "王五", "delta": None})
    assert text == "王五 分  分"


def test_consume_fixed_window_zero_limit_allows() -> None:
    # 限流上限为 0 视为不限制，直接放行
    assert consume_fixed_window("u1:mastery_gap", limit=0, window_seconds=3600) is True


def test_consume_fixed_window_unique_key_allowed() -> None:
    # 每次使用唯一键第一次访问应放行（limit>=1 时），避免测试间互相干扰
    unique_key = f"test:{__import__('uuid').uuid4().hex}"
    assert consume_fixed_window(unique_key, limit=1, window_seconds=3600) is True


def test_score_bucket_by_ratio() -> None:
    assert _score_bucket(95, 100) == "优秀"
    assert _score_bucket(80, 100) == "良好"
    assert _score_bucket(70, 100) == "中等"
    assert _score_bucket(60, 100) == "及格"
    assert _score_bucket(59, 100) == "待提升"
    assert _score_bucket(30, 50) == "及格"  # 30/50=0.6


def _grading_record(status, score=None, total_score=None):
    return SimpleNamespace(status=status, score=score, total_score=total_score)


def test_compute_grading_stats_basic() -> None:
    records = [
        _grading_record("graded", 95, 100),   # 优秀
        _grading_record("graded", 55, 100),   # 待提升
        _grading_record("graded", 70, 100),   # 中等
        _grading_record("pending"),
        _grading_record("pending"),
    ]
    stats = _compute_grading_stats(records)
    assert stats["total"] == 5
    assert stats["graded"] == 3
    assert stats["pending"] == 2
    assert stats["avg_score"] == round((95 + 55 + 70) / 3, 1)
    assert stats["pass_rate"] == round(2 / 3, 2)  # 95、70 及格，55 不及格
    assert stats["grading_rate"] == 60.0
    assert stats["score_distribution"] == {"待提升": 1, "及格": 0, "中等": 1, "良好": 0, "优秀": 1}


def test_compute_grading_stats_empty() -> None:
    stats = _compute_grading_stats([])
    assert stats["total"] == 0
    assert stats["graded"] == 0
    assert stats["avg_score"] == 0
    assert stats["pass_rate"] == 0
    assert stats["grading_rate"] == 0
    assert stats["score_distribution"] == {"待提升": 0, "及格": 0, "中等": 0, "良好": 0, "优秀": 0}
