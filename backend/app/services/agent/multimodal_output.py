"""多模态智能辅导输出节点（T-B-03）。

本模块是「多模态输出节点」的载体：为「代码辅导」「图解生成」两个意图封装 system
prompt 模板与输出格式硬约束。轻量方案下不碰流式分块与前端渲染，只负责把模型输出
约束为「文字段落 + 代码块 + Mermaid 图解」的混合 Markdown，沿用现有 WebSocket
text_delta 事件下发，前端按 Markdown 渲染（Mermaid/代码块的高保真渲染属 T-C-03）。

设计取舍：
- 不做流式 Markdown 围栏块实时解析（增量状态机易碎、收益有限），改用 prompt 硬约束
  模型输出合法围栏块，前端缓冲整段后渲染。
- 编排层（AiOrchestratorService / IntentRouter 2.0）不识别这两个意图，一律按
  default_chat 下发到 workflow，由 workflow._node_route 在图内路由。因此本模块只被
  workflow._build_model_messages 调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.common import Citation
from app.services.shared.citation_context import build_llm_context

if TYPE_CHECKING:
    # 仅用于类型注解，避免运行时导入开销与潜在循环。
    from app.services.course.context import CourseContext
    from app.services.profile.repository import ProfileContext


# 代码辅导意图的输出格式硬约束。语言名必填是为了前端代码高亮；逐行标注要求是为了
# 让学生看到问题定位而非一段笼统说明。
_CODE_TUTOR_SYSTEM_TEMPLATE = """你是高校课程级个性化学习平台中的编程辅导助教。
当前任务：代码辅导。请围绕学生给出的代码、报错或实现需求作答。

输出格式硬约束（必须遵守，便于前端按代码块高亮渲染）：
1. 代码一律使用三引号围栏块，且必须写明语言名，例如：
   ```python
   def foo():
       pass
   ```
2. 诊断报错时：先复述学生原代码片段（保留原样），再逐行标注问题行号与原因，最后给修复方案。
3. 修复方案必须是完整可运行代码块，不要只给片段或省略号。
4. 解释性文字用普通段落包裹代码块，先给结论（什么问题/怎么解决），再分步解释原因、例子和下一步练习。
5. 禁止用图片链接、SVG 或外部资源；只用 Markdown 文字与代码块。

学术诚信与引用约束：
- 没有课程资料引用时，禁止编造教材页码、论文、实验数据或文档来源。
- 若下方提供了课程引用材料，在涉及课程事实时用“引用 1/2/3”的方式提示依据。
{profile_rule}{course_context}{citation_rule}"""

# 图解生成意图的输出格式硬约束。Mermaid 语法可渲染是核心要求，避免节点 id 含空格、
# 箭头方向非法等导致前端渲染失败的常见错误。
_DIAGRAM_GENERATION_SYSTEM_TEMPLATE = """你是高校课程级个性化学习平台中的知识结构可视化助教。
当前任务：图解生成。请把学生问题中的概念关系、流程或结构画成 Mermaid 图解。

输出格式硬约束（必须遵守，便于前端按 mermaid 渲染）：
1. 图解必须使用三引号 mermaid 围栏块：
   ```mermaid
   flowchart TD
       A[输入] --> B[隐藏层]
       B --> C[输出]
   ```
2. 优先图类型：flowchart TD（流程）、sequenceDiagram（时序）、classDiagram（类关系）、
   stateDiagram-v2（状态）、mindmap（知识脉络）。按问题性质选择最合适的一种。
3. Mermaid 语法必须可渲染：
   - 节点 id 不含空格或特殊字符（用 A、B、node1 等，标签文字放方括号内）；
   - 箭头方向合法（-->、---、-.->等），不要写多余空格；
   - 括号、方括号配对；不要多余缩进；不要在图里混入 Markdown。
4. 每个 mermaid 块前后用一两句文字解释图意与阅读顺序。
5. 若一个图不足以表达，可输出多个 mermaid 块 + 文字串联，但每图都要能独立渲染。
6. 禁止用图片链接、SVG、外链或 base64；只用 mermaid 文本 + Markdown 文字。

学术诚信与引用约束：
- 没有课程资料引用时，不要伪造教材页码、论文、实验数据或文档来源。
- 若下方提供了课程引用材料，在涉及课程事实时用“引用 1/2/3”的方式提示依据。
{profile_rule}{course_context}{citation_rule}"""


def _build_profile_rule(profile_context: "ProfileContext | None") -> str:
    """把学习画像拼成只供模型内部参考的提示块，禁止原样输出给学生。"""
    if not profile_context:
        return "\n内部画像上下文：暂无画像摘要，按通用深度讲解。"
    profile_text = profile_context.format_for_prompt()
    return (
        "\n内部画像上下文（只用于调整讲解深度、例子、术语密度和资源形式，禁止原样输出给学生）：\n"
        f"{profile_text}"
    )


def _build_course_context(context: "CourseContext | None", learning_scope: str) -> str:
    """拼接当前课程/知识点上下文；通用学习场景下省略课程信息。"""
    if learning_scope == "general" or not context:
        return "\n当前场景：通用学习（不绑定课程）。"
    concept = context.concept_id or "未指定"
    return (
        f"\n当前课程：{context.course_title}\n"
        f"当前知识点：{concept}"
    )


def _build_citation_rule(citations: list[Citation]) -> str:
    """构建课程引用材料块；空引用时给出空依据提示。"""
    citation_text = build_llm_context(citations)
    if not citation_text.strip():
        return "\n课程引用材料：无（不要伪造来源）。"
    return f"\n课程引用材料：\n{citation_text}"


def build_multimodal_system_prompt(
    intent: str,
    context: "CourseContext | None",
    profile_context: "ProfileContext | None",
    citations: list[Citation],
    learning_scope: str,
) -> str:
    """为代码辅导/图解生成意图组装 system prompt。

    参数:
        intent: 意图标识，仅接受 "code_tutor" 或 "diagram_generation"。
        context: 课程上下文，通用场景可为 None。
        profile_context: 学习画像上下文，用于调整讲解深度，None 表示无画像。
        citations: 课程引用材料列表，空列表表示无课程依据。
        learning_scope: 学习范围，"general" 或 "course"。

    返回:
        组装好的 system prompt 字符串。

    失败模式:
        传入未支持的 intent 时抛出 ValueError，由调用方暴露配置错误，
        不做静默降级以免意图路由异常被掩盖。
    """
    profile_rule = _build_profile_rule(profile_context)
    course_context = _build_course_context(context, learning_scope)
    citation_rule = _build_citation_rule(citations)

    if intent == "code_tutor":
        template = _CODE_TUTOR_SYSTEM_TEMPLATE
    elif intent == "diagram_generation":
        template = _DIAGRAM_GENERATION_SYSTEM_TEMPLATE
    else:
        raise ValueError(
            f"不支持的多模态意图：{intent}，仅接受 code_tutor / diagram_generation"
        )
    return template.format(
        profile_rule=profile_rule,
        course_context=course_context,
        citation_rule=citation_rule,
    )
