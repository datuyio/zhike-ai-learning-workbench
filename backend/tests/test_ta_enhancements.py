"""助教端 Wave 0 纯逻辑单元测试：班级对比 / 学生趋势 / 热力图 / 新预警规则 / 批改统计增强。"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.api.v1.routes.ta import (
    _avg_mastery_per_student,
    _build_compare_rows,
    _build_trend_series,
    _compute_heatmap_matrix,
    _compute_grading_stats,
    _pick_late_submission_candidates,
    _pick_resource_idle_candidates,
)


def _row(student_id, mastery):
    return SimpleNamespace(user_id=student_id, mastery=mastery)


def test_avg_mastery_groups_by_student() -> None:
    rows = [_row("s1", 60), _row("s1", 90), _row("s2", 50)]
    result = _avg_mastery_per_student(rows)
    assert result == {"s1": 75, "s2": 50}


def test_avg_mastery_empty() -> None:
    assert _avg_mastery_per_student([]) == {}


def _compare_row(**overrides):
    base = {
        "class_id": "c1", "name": "一班", "avg_score": 0.0, "avg_mastery": 0,
        "weak_points": 0, "active_students": 0, "student_count": 0,
    }
    base.update(overrides)
    return base


def test_compare_rows_sorted_by_mastery_desc() -> None:
    rows = [
        _compare_row(class_id="c1", name="一班", avg_mastery=70),
        _compare_row(class_id="c2", name="二班", avg_mastery=85),
    ]
    result = _build_compare_rows(rows)
    assert [r["class_id"] for r in result] == ["c2", "c1"]


def test_compare_rows_respects_top_n_and_rounds_score() -> None:
    rows = [_compare_row(avg_score=82.44, avg_mastery=m) for m in (50, 60)]
    result = _build_compare_rows(rows, top_n=1)
    assert len(result) == 1
    assert result[0]["avg_score"] == 82.4


def test_compare_rows_empty() -> None:
    assert _build_compare_rows([]) == []


def test_trend_series_fills_missing_days() -> None:
    today = date(2026, 8, 6)
    series = _build_trend_series(
        days=3,
        score_by_day={"2026-08-05": (0.8, 1), "2026-08-06": (0.5, 1)},
        event_by_day={"2026-08-06": 2},
        today=today,
    )
    assert [s["date"] for s in series] == ["2026-08-04", "2026-08-05", "2026-08-06"]
    assert series[0]["score"] is None
    assert series[0]["event_count"] == 0
    assert series[1]["score"] == 0.8
    assert series[2]["score"] == 0.5
    assert series[2]["event_count"] == 2


def test_trend_series_empty_days() -> None:
    today = date(2026, 8, 6)
    series = _build_trend_series(3, {}, {}, today=today)
    assert len(series) == 3
    assert all(s["score"] is None and s["event_count"] == 0 for s in series)


def test_heatmap_matrix_2x2_with_missing_filled_zero() -> None:
    rows = [("s1", "cA", 80), ("s1", "cB", 50), ("s2", "cA", 60)]
    result = _compute_heatmap_matrix(rows)
    assert result["students"] == ["s1", "s2"]
    assert result["concepts"] == ["cA", "cB"]
    assert result["matrix"] == [[80, 50], [60, 0]]


def test_heatmap_matrix_empty() -> None:
    assert _compute_heatmap_matrix([]) == {"students": [], "concepts": [], "matrix": []}


def _grading_record(is_late, title="作业", created_at=None):
    return SimpleNamespace(
        is_late=is_late, title=title, score=80, total_score=100,
        created_at=created_at or datetime.now(timezone.utc),
    )


def test_late_candidates_only_students_with_late_records() -> None:
    by_student = {
        "s1": [_grading_record(True), _grading_record(False)],
        "s2": [_grading_record(False)],
    }
    result = _pick_late_submission_candidates(by_student, {"s1": "张三", "s2": "李四"})
    assert [c["student_id"] for c in result] == ["s1"]
    assert result[0]["student_name"] == "张三"
    assert result[0]["count"] == 1


def test_late_severity_high_for_three_or_more() -> None:
    by_student = {"s1": [_grading_record(True) for _ in range(3)]}
    result = _pick_late_submission_candidates(by_student, {"s1": "张三"})
    assert result[0]["severity"] == "high"


def test_resource_idle_requires_history_and_window() -> None:
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    stale = now - timedelta(days=30)
    stat = {
        "s1": (stale, True),    # 有历史且 30 天未查阅 → 候选
        "s2": (recent, True),   # 有历史但 1 天前刚查阅 → 跳过
        "s3": (None, False),    # 无历史 → 跳过
    }
    result = _pick_resource_idle_candidates(stat, {"s1": "张三"}, now, idle_days=7)
    assert [c["student_id"] for c in result] == ["s1"]


def _grecord(question_type, status="graded", score=None, total=100):
    return SimpleNamespace(
        question_type=question_type, status=status, score=score,
        total_score=total,
    )


def test_grading_stats_by_question_type() -> None:
    records = [
        _grecord("single_choice", score=80),
        _grecord("single_choice", score=90),
        _grecord("short_answer", score=60),
        _grecord("single_choice", status="pending"),
    ]
    result = _compute_grading_stats(records)
    assert result["by_question_type"] == {
        "single_choice": {"count": 2, "avg_score": 85.0},
        "short_answer": {"count": 1, "avg_score": 60.0},
    }


def test_grading_stats_unknown_type_fallback() -> None:
    records = [_grecord(None, score=80)]
    result = _compute_grading_stats(records)
    assert result["by_question_type"] == {"unknown": {"count": 1, "avg_score": 80.0}}
