"""智能备课纯逻辑单元测试：教案降级骨架、LLM 输出有效性、检索注入与图片批改 prompt。"""
from types import SimpleNamespace

from app.api.v1.routes.ta import (
    _fallback_lesson_outline,
    _format_citations_for_prompt,
    _grading_policy,
    _is_valid_llm_outline,
    _lesson_plan_generation_messages,
    _vision_grading_prompt,
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


def test_is_valid_llm_outline_success_long_enough() -> None:
    answer = (
        "# 第3章 反向传播\n\n"
        "## 教学目标\n\n"
        "掌握反向传播算法的推导与实现，能手工完成两层网络的梯度计算，"
        "理解链式法则在深度学习中的作用。\n\n"
        "## 教学重点难点\n\n"
        "重点：链式法则与梯度逐层回传；难点：多层网络的梯度消失现象。\n\n"
        "## 教学过程\n\n"
        "1. 复习前向传播；2. 讲解反向传播推导；3. 动手实现两层神经网络。\n\n"
        "## 作业布置\n\n"
        "完成课后习题，并实现一个两层神经网络验证梯度正确性。\n\n"
        "## 板书设计\n\n"
        "板书按公式推导流程逐步展开。\n"
    )
    assert _is_valid_llm_outline(_fake_result("success", answer)) is True


def test_is_valid_llm_outline_fallback_status_rejected() -> None:
    # 网关降级返回 status="fallback"（不抛异常），必须被识别为降级而非 LLM 成功
    assert _is_valid_llm_outline(_fake_result("fallback", "模型网关暂时无法完成真实模型调用……")) is False


def test_is_valid_llm_outline_too_short_rejected() -> None:
    assert _is_valid_llm_outline(_fake_result("success", "短")) is False


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
