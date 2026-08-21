"""助教端雷达图纯逻辑单元测试：学生五维评分计算。"""
from app.api.v1.routes.ta import _build_student_radar_dimensions


def _dims(**overrides) -> list[dict]:
    base = dict(
        assessment_scores=[], mastery_values=[], homework_ratios=[],
        resource_view_count=0, total_event_count=0, active_days=0, period_days=14,
    )
    base.update(overrides)
    return _build_student_radar_dimensions(**base)


def test_quiz_uses_assessment_scores_when_present() -> None:
    dims = _dims(assessment_scores=[70.0, 80.0, 90.0], mastery_values=[55.0])
    quiz = next(d for d in dims if d["key"] == "quiz")
    assert quiz["score"] == 80
    assert quiz["source"] == "assessment"


def test_quiz_falls_back_to_mastery_without_assessments() -> None:
    dims = _dims(mastery_values=[60.0, 80.0])
    quiz = next(d for d in dims if d["key"] == "quiz")
    assert quiz["score"] == 70
    assert quiz["source"] == "mastery_fallback"


def test_quiz_no_data_without_either() -> None:
    quiz = next(d for d in _dims() if d["key"] == "quiz")
    assert quiz["score"] == 0
    assert quiz["source"] == "no_data"


def test_homework_averages_ratio() -> None:
    # 得分率 0.8 与 0.9 → 平均 0.85 → 85 分
    dims = _dims(homework_ratios=[0.8, 0.9])
    homework = next(d for d in dims if d["key"] == "homework")
    assert homework["score"] == 85
    assert homework["source"] == "grading"


def test_homework_no_data_without_graded_records() -> None:
    homework = next(d for d in _dims() if d["key"] == "homework")
    assert homework["score"] == 0
    assert homework["source"] == "no_data"


def test_resource_and_activity_scale_and_clamp() -> None:
    # 资料 10 次 / 封顶 20 → 50；事件 60 个 / 封顶 50 → 100（截断）
    dims = _dims(resource_view_count=10, total_event_count=60, active_days=14)
    by_key = {d["key"]: d for d in dims}
    assert by_key["resource"]["score"] == 50
    assert by_key["activity"]["score"] == 100
    assert by_key["consistency"]["score"] == 100
    assert by_key["resource"]["source"] == "events"


def test_consistency_is_active_days_ratio() -> None:
    dims = _dims(total_event_count=10, active_days=7)
    consistency = next(d for d in dims if d["key"] == "consistency")
    assert consistency["score"] == 50


def test_all_no_data_when_no_events() -> None:
    by_key = {d["key"]: d for d in _dims()}
    assert by_key["resource"]["score"] == 0 and by_key["resource"]["source"] == "no_data"
    assert by_key["activity"]["score"] == 0 and by_key["activity"]["source"] == "no_data"
    assert by_key["consistency"]["score"] == 0 and by_key["consistency"]["source"] == "no_data"
