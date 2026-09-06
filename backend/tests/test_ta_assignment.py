"""助教端 Wave 1 纯逻辑单元测试：逾期判定 / 成绩 CSV 行 / 批改导出 CSV 行。"""
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.routes.ta._shared import _compute_is_late, _require_uuid, _resolve_submission_delta
from app.api.v1.routes.ta.assignments import _build_grades_csv_rows
from app.api.v1.routes.ta.grading import _build_grading_export_rows


def test_require_uuid_valid_returns_uuid() -> None:
    value = str(uuid_mod.uuid4())
    assert _require_uuid(value, "班级不存在") == uuid_mod.UUID(value)


def test_require_uuid_invalid_string_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _require_uuid("nonexistent-id", "班级不存在")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "班级不存在"


def test_require_uuid_none_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _require_uuid(None, "班级不存在")  # type: ignore[arg-type]
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "班级不存在"


def test_require_uuid_non_string_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _require_uuid(123, "班级不存在")  # type: ignore[arg-type]
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "班级不存在"


def test_require_uuid_accepts_uuid_object() -> None:
    """已解析的 UUID 对象直接透传，不误判 404。"""
    value = uuid_mod.uuid4()
    assert _require_uuid(value, "班级不存在") is value


def test_require_uuid_normalizes_string_case() -> None:
    """合法但大小写不同的 UUID 字符串统一解析为规范形式。"""
    value = uuid_mod.uuid4()
    assert _require_uuid(str(value).upper(), "班级不存在") == value


def test_is_late_false_without_due_date() -> None:
    now = datetime.now(timezone.utc)
    assert _compute_is_late(None, now) is False


def test_is_late_false_before_due() -> None:
    now = datetime.now(timezone.utc)
    assert _compute_is_late(now + timedelta(hours=1), now) is False


def test_is_late_true_after_due() -> None:
    now = datetime.now(timezone.utc)
    assert _compute_is_late(now - timedelta(hours=1), now) is True


def test_resolve_delta_new_submission() -> None:
    assert _resolve_submission_delta(None) == 1


def test_resolve_delta_resubmission_increments() -> None:
    assert _resolve_submission_delta(1) == 2
    assert _resolve_submission_delta(3) == 4


def test_grades_csv_rows_header_and_avg() -> None:
    students = [("s1", "张三"), ("s2", "李四")]
    titles = ["作业A", "作业B"]
    score_map = {("s1", "作业A"): 90.0, ("s1", "作业B"): 80.0, ("s2", "作业A"): 60.0}
    total_map = {("s1", "作业A"): 100.0, ("s1", "作业B"): 100.0, ("s2", "作业A"): 100.0}
    rows = _build_grades_csv_rows(students, titles, score_map, total_map)
    assert rows[0] == ["学生", "学生ID", "作业A", "作业B", "平均分"]
    assert rows[1] == ["张三", "s1", 90.0, 80.0, 85.0]
    assert rows[2] == ["李四", "s2", 60.0, "", 60.0]


def test_grades_csv_rows_normalizes_avg_by_total() -> None:
    students = [("s1", "张三")]
    titles = ["作业A", "作业B"]
    score_map = {("s1", "作业A"): 90.0, ("s1", "作业B"): 9.0}
    total_map = {("s1", "作业A"): 100.0, ("s1", "作业B"): 10.0}
    rows = _build_grades_csv_rows(students, titles, score_map, total_map)
    # 90/100 与 9/10 均 90%，归一化平均 = 90.0（原始算术平均会误算为 49.5）
    assert rows[1][-1] == 90.0


def test_grades_csv_rows_no_assignments() -> None:
    rows = _build_grades_csv_rows([("s1", "张三")], [], {}, {})
    assert rows[0] == ["学生", "学生ID", "平均分"]


def test_grading_export_rows() -> None:
    record = SimpleNamespace(
        id="r1", title="作业A", student_name="张三", class_name="一班",
        question_type="short_answer", score=85.0, total_score=100.0,
        status="graded", is_late=True,
        created_at=datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc),
    )
    rows = _build_grading_export_rows([record])
    assert rows[0][0] == "记录ID"
    assert rows[1] == ["r1", "作业A", "张三", "一班", "short_answer", 85.0, 100.0, "graded", "是", "2026-08-05 10:00"]
