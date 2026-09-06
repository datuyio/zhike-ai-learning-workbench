"""智能备课纯逻辑单元测试：教案降级骨架、LLM 输出解析、检索注入与图片批改 prompt。"""
import json
from types import SimpleNamespace

from app.api.v1.routes.ta.grading import _grading_policy, _vision_grading_prompt
from app.api.v1.routes.ta.lesson_plans import (
    _fallback_lesson_outline,
    _format_citations_for_prompt,
    _lesson_plan_generation_messages,
    _parse_lesson_plan_json,
)


def _citation(title: str, content: str | None = None, snippet: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(source_title=title, content=content, snippet=snippet)


def test_fallback_lesson_outline_contains_title_and_sections() -> None:
    outline = _fallback_lesson_outline("第3章 反向传播")
    assert outline.startswith("# 第3章 反向传播")
    for section in ["## 教学目标", "## 教学重点难点", "## 教学过程", "## 作业布置", "## 板书设计"]:
        assert section in outline


def test_fallback_lesson_outline_order() -> None:
    outline = _fallback_lesson_outline("标题")
    sections = ["## 教学目标", "## 教学重点难点", "## 教学过程", "## 作业布置", "## 板书设计"]
    positions = [outline.index(section) for section in sections]
    assert positions == sorted(positions)


def _fake_result(status: str, answer: str):
    return SimpleNamespace(status=status, answer=answer)


def test_parse_lesson_plan_json_success() -> None:
    raw = json.dumps({
        "objectives": ["掌握反向传播"],
        "key_points": ["链式法则"],
        "difficulties": ["梯度消失"],
        "process": [{"step": "引入", "content": "复习前向传播", "duration": "5分钟"}],
        "homework": "完成课后习题",
        "board": "公式推导",
    }, ensure_ascii=False)
    parsed = _parse_lesson_plan_json(raw)
    assert parsed is not None
    assert parsed["objectives"] == ["掌握反向传播"]
    assert parsed["process"][0]["step"] == "引入"


def test_parse_lesson_plan_json_rejects_invalid() -> None:
    # 缺 objectives 锚点或非法 JSON 必须返回 None，绝不把不可解析结果当作成功
    assert _parse_lesson_plan_json('{"key_points": ["链式法则"]}') is None
    assert _parse_lesson_plan_json("模型网关暂时无法完成真实模型调用……") is None
    assert _parse_lesson_plan_json(None) is None


def test_format_citations_empty_returns_empty() -> None:
    assert _format_citations_for_prompt([]) == ""


def test_format_citations_uses_content_or_snippet() -> None:
    citations = [
        _citation("导数的定义", "导数描述了函数的变化率。"),
        _citation("链式法则", None, snippet="链式法则用于复合函数求导。"),
    ]
    text = _format_citations_for_prompt(citations)
    assert "[1]《导数的定义》" in text
    assert "导数描述了函数的变化率" in text
    assert "[2]《链式法则》" in text
    assert "链式法则用于复合函数求导" in text


def test_format_citations_truncates_long_content() -> None:
    citation = _citation("长文", "x" * 1000)
    text = _format_citations_for_prompt([citation], char_limit=100)
    assert "……" in text
    assert text.count("x") == 100


def test_lesson_plan_messages_with_retrieval_context() -> None:
    messages = _lesson_plan_generation_messages("高等数学", "第3章 导数", "导数", "要包含例题", "[1]《教材》\n导数内容")
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "高等数学" in user
    assert "第3章 导数" in user
    assert "要包含例题" in user
    assert "检索内容" in user
    assert "《教材》" in user


def test_lesson_plan_messages_without_retrieval_context() -> None:
    messages = _lesson_plan_generation_messages("高数", "教案", None, None, "")
    user = messages[1]["content"]
    assert "检索内容" not in user


def test_vision_grading_prompt_contains_contract() -> None:
    prompt = _vision_grading_prompt("选择题", "single_choice", 10, _grading_policy("single_choice"))
    assert "题目：选择题" in prompt
    assert "评分口径：单选题按标准答案严格计分" in prompt
    assert '{"score"' in prompt
    assert "图片无法识别" in prompt
    assert "不要 Markdown" in prompt


def test_grading_policy_fallback_default() -> None:
    assert "要点完整度" in _grading_policy(None)
    assert "要点完整度" in _grading_policy("unknown_type")
