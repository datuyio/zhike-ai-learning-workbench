"""学情诊断纯逻辑单元测试：薄弱点聚合、强度分级、班级指标与诊断降级文案。"""
from types import SimpleNamespace

from app.api.v1.routes.ta._shared import _weakness_severity
from app.api.v1.routes.ta.alerts import _mastery_gap_candidates
from app.api.v1.routes.ta.diagnosis import (
    _aggregate_class_metrics,
    _aggregate_weak_points,
    _diagnosis_fallback,
    _diagnosis_messages,
    _parse_diagnosis_text,
    _suggested_practice,
    _top_weak_concepts,
)


def test_aggregate_weak_points_avg_and_weak_count() -> None:
    # c1: (90, 30, 55) 平均 58.33 → weak_rate 0.42；低于 60 阈值的有 2 个
    # c2: (80, 80) 平均 80.0 → weak_rate 0.20；0 个薄弱
    rows = [("c1", 90), ("c1", 30), ("c1", 55), ("c2", 80), ("c2", 80)]
    titles = {"c1": "知识点一", "c2": "知识点二"}
    result = _aggregate_weak_points(rows, titles)
    assert [item["concept_id"] for item in result] == ["c1", "c2"]  # 平均掌握度低者排前
    assert result[0]["concept"] == "知识点一"
    assert result[0]["weak_rate"] == 0.42
    assert result[0]["student_count"] == 2
    assert result[1]["weak_rate"] == 0.2
    assert result[1]["student_count"] == 0


def test_aggregate_weak_points_missing_title_falls_back_to_id() -> None:
    result = _aggregate_weak_points([("c-unknown", 40)], {})
    assert result[0]["concept"] == "c-unknown"
    assert result[0]["weak_rate"] == 0.6
    assert result[0]["student_count"] == 1


def test_aggregate_weak_points_truncates_top_n() -> None:
    rows = [(f"c{i}", float(20 + i)) for i in range(15)]
    result = _aggregate_weak_points(rows, {})
    assert len(result) == 10


def test_aggregate_weak_points_empty() -> None:
    assert _aggregate_weak_points([], {}) == []


def test_weakness_severity_tiers() -> None:
    assert _weakness_severity(35) == "严重"
    assert _weakness_severity(50) == "中等"
    assert _weakness_severity(65) == "轻微"
    assert _weakness_severity(80) == "正常"


def test_suggested_practice_clamped_range() -> None:
    assert 3 <= _suggested_practice(0.1) <= 10
    assert _suggested_practice(0.42) == 5
    assert _suggested_practice(1.0) == 10
    assert _suggested_practice(0.0) == 3


def test_aggregate_weak_points_includes_severity() -> None:
    # c1 平均 (90+30+55)/3=58.33 → 轻微；c2 平均 80 → 正常
    rows = [("c1", 90), ("c1", 30), ("c1", 55), ("c2", 80), ("c2", 80)]
    result = _aggregate_weak_points(rows, {"c1": "知识点一", "c2": "知识点二"})
    by_id = {item["concept_id"]: item for item in result}
    assert by_id["c1"]["severity"] == "轻微"
    assert by_id["c2"]["severity"] == "正常"
    assert "suggested_practice" in by_id["c1"]


def test_aggregate_class_metrics_from_pairs() -> None:
    rows = [("c1", 90), ("c1", 30), ("c1", 55), ("c2", 80), ("c2", 80)]
    metrics = _aggregate_class_metrics(rows, student_count=3)
    assert metrics["concepts_total"] == 2
    assert metrics["student_count"] == 3
    assert metrics["weak_concepts"] == 1  # 只有 c1 平均 58.33 低于 60
    assert metrics["avg_mastery"] == round((58.33 + 80) / 2)
    assert metrics["weak_rate"] == round(1 - ((58.33 + 80) / 2) / 100, 2)
    assert metrics["mastered_ratio"] == 0.5


def test_aggregate_class_metrics_empty() -> None:
    metrics = _aggregate_class_metrics([], 5)
    assert metrics["concepts_total"] == 0
    assert metrics["student_count"] == 5


def test_top_weak_concepts_orders_by_lowest_mastery() -> None:
    rows = [("c1", 90), ("c2", 30), ("c3", 55)]
    result = _top_weak_concepts(rows, {"c2": "知识点二", "c3": "知识点三"})
    assert [item["concept_id"] for item in result] == ["c2", "c3", "c1"]
    assert result[0]["concept"] == "知识点二"
    assert result[0]["avg_mastery"] == 30


def test_parse_diagnosis_text_valid() -> None:
    raw = '{"summary": "整体需加强", "suggestions": ["补基础", "多练习"]}'
    parsed = _parse_diagnosis_text(raw)
    assert parsed["summary"] == "整体需加强"
    assert parsed["suggestions"] == ["补基础", "多练习"]


def test_parse_diagnosis_text_invalid() -> None:
    assert _parse_diagnosis_text("无法解析") is None
    assert _parse_diagnosis_text('{"suggestions": []}') is None  # 缺 summary


def test_parse_diagnosis_text_rejects_template_placeholders() -> None:
    # 模型照抄模板占位文案时应返回 None，触发规则降级
    raw = '{"summary": "一段班级学情总结（1-3 句）", "suggestions": ["建议1", "建议2", "建议3"]}'
    assert _parse_diagnosis_text(raw) is None


def test_parse_diagnosis_text_filters_placeholder_suggestions() -> None:
    # 总结有效、建议混入占位项时应过滤占位项
    raw = '{"summary": "整体需加强", "suggestions": ["补基础", "建议1", "多练习"]}'
    parsed = _parse_diagnosis_text(raw)
    assert parsed["summary"] == "整体需加强"
    assert parsed["suggestions"] == ["补基础", "多练习"]


def test_diagnosis_fallback_with_data() -> None:
    metrics = {
        "student_count": 30, "concepts_total": 10, "avg_mastery": 55,
        "weak_concepts": 4, "weak_rate": 0.45, "mastered_ratio": 0.6,
    }
    fallback = _diagnosis_fallback(metrics, [{"concept": "导数", "avg_mastery": 40}])
    assert "平均掌握度约 55%" in fallback["summary"]
    assert "4 个知识点" in fallback["summary"]
    assert "导数" in fallback["suggestions"][0]


def test_diagnosis_fallback_empty() -> None:
    fallback = _diagnosis_fallback(
        {"student_count": 0, "concepts_total": 0, "avg_mastery": 0, "weak_concepts": 0, "weak_rate": 0.0, "mastered_ratio": 0.0},
        [],
    )
    assert "暂无掌握度数据" in fallback["summary"]


def test_diagnosis_messages_injects_metrics_and_priority() -> None:
    metrics = {
        "student_count": 30, "concepts_total": 10, "avg_mastery": 55,
        "weak_concepts": 4, "weak_rate": 0.45, "mastered_ratio": 0.6,
    }
    priority = [{"concept": "导数", "avg_mastery": 40}]
    messages = _diagnosis_messages(metrics, priority)
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "平均掌握度 55%" in user
    assert "薄弱知识点数（<60%）4" in user
    assert "导数（平均掌握度 40%）" in user
    assert '"summary"' in user


def _mastery_row(user_id, concept_id, mastery):
    return SimpleNamespace(user_id=user_id, concept_id=concept_id, mastery=mastery)


def test_mastery_gap_candidates_weakest_per_student() -> None:
    rows = [
        _mastery_row("u1", "c1", 90),
        _mastery_row("u1", "c2", 35),   # u1 最弱且低于阈值
        _mastery_row("u2", "c1", 80),   # u2 均达标，不应成为候选
    ]
    candidates = _mastery_gap_candidates(rows, {"u1": "学生一", "u2": "学生二"}, {"c2": "知识点二"})
    assert len(candidates) == 1
    assert candidates[0]["student_id"] == "u1"
    assert candidates[0]["concept"] == "知识点二"
    assert candidates[0]["severity"] == "严重"  # 35 < 40 → 严重

