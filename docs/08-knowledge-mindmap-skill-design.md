# 知识思维导图 Skill 设计

## 1. 定位

`knowledge-mindmap` 是资源生成体系中的专用 Skill，对应现有资源类型 `resource_type = "mindmap"`。它负责把课程知识点、课程资料依据、学习路径节点和学生画像压缩成可预览、可编辑、可保存、可审核的知识思维导图。

该 Skill 不替代课程资料问答，也不直接调用 Cloud RAG 生成正文。正确链路仍是：

```text
ResourceAgent
  -> 可选 CloudRagProvider 获取课程依据（local_pgvector 模式由本地知识库适配器检索）
  -> ChatProvider 生成导图正文
  -> VerifyAgent 核验结构、引用和难度
  -> ArtifactCanvas 预览与保存
```

本地 `local_pgvector` 语料可先由 `backend/scripts/sync_local_documents_to_concepts.py` 映射为 `CourseConcept`、`CourseSection` 和切片关联；学习路径节点会携带这些 `concept_id`，因此思维导图生成可直接定位到本地知识库中的具体知识点。

默认输出为 Mermaid mindmap 源码，并使用 JSON 外壳承载 `source_code`，优先复用现有 ArtifactCanvas、ResourceVersion 和资源审核流程；旧版 Markmap 兼容 Markdown 资源仅作为前端兼容预览输入保留。

## 2. 触发条件

显式触发优先级最高：

```json
{
  "action_type": "resource_generation",
  "resource_type": "mindmap"
}
```

自然语言触发关键词：

* “生成思维导图”
* “画一个知识脑图”
* “梳理知识结构”
* “整理知识点关系”
* “给我一张学习路线图”
* “把这一章做成导图”

如果用户只是问“这个知识点是什么”，默认仍走普通 Chat；只有明确要求资源生成或页面入口触发资源生成时，才创建 ResourceTaskCard。

## 3. 输入契约

直接复用 `ResourceGenerateRequest`，并对字段做以下约束：

```ts
interface KnowledgeMindmapSkillInput {
  scope: 'course' | 'general'
  course_id?: string | null
  concept_id?: string | null
  path_node_id?: string | null
  resource_type: 'mindmap'
  difficulty: 'basic' | 'medium' | 'advanced'
  goal: string
  requirements?: string | null
  topic?: string | null
  need_course_evidence: boolean
}
```

Skill 执行时还应读取：

* `profile_summary`：全局画像、课程画像、当前会话画像的摘要。
* `mastery_context`：当前课程下掌握度最低或最相关的知识点。
* `recent_dialog`：最近对话中暴露出的困惑、偏好和目标。
* `citations`：课程资料检索片段，最多 5 条进入 prompt，完整引用进入任务元信息和右侧引用面板。

## 4. 输出契约

正文只输出一个 JSON 对象，不输出 Markdown 代码块、HTML、表格或生成过程说明。`source_code` 字段承载 Mermaid mindmap 源码，便于后端做结构化校验、失败重试和审核归档。

基础结构：

```json
{
  "chart_type": "mindmap",
  "syntax": "mermaid",
  "source_code": "mindmap\n  root((知识点名称))\n    定义\n      用一句话说明核心含义\n    前置知识\n      必须先懂的概念\n    关键步骤\n      第一步\n    常见误区\n      容易混淆点\n    练习\n      基础自检\n    与后续章节关系\n      关联章节"
}
```

格式硬约束：

* JSON 顶层必须只有 `chart_type`、`syntax`、`source_code` 三个字段。
* `chart_type` 固定为 `mindmap`，`syntax` 固定为 `mermaid`。
* `source_code` 第一行固定为 `mindmap`，第二行使用 `root((知识点名称))`。
* 默认只使用 root、主要分支、短节点说明三层，避免超过 3 层导致导图拥挤。
* 二级节点建议 5 到 8 个，必须覆盖定义、前置、关键步骤、常见误区、练习、与后续章节关系。
* 每个节点应短句化，建议不超过 28 个中文字符。
* 节点文本禁止花括号、尖括号、竖线、反引号、Markdown 标题符号等 Mermaid 易冲突字符。
* 不要在正文里逐条复制引用片段；引用展示交给 `citations` 元信息。
* 不要输出“检索到/未检索到/根据资料”等内部过程描述。

## 5. 个性化规则

Skill 必须根据画像调整导图结构，而不是只改变措辞。

| 画像信号 | 导图调整 |
|---|---|
| 基础薄弱 | 增加“前置知识”“学习步骤”，减少抽象术语密度。 |
| 图解型 | 保持层级清晰，增加关系、对比、流程节点。 |
| 代码实践型 | 增加“代码视角”或“动手任务”分支。 |
| 公式推导型 | 增加“变量含义”“公式位置”“推导顺序”分支。 |
| 易错点明显 | 强化“常见误区”“判断方法”“自检题”。 |
| 项目/求职目标 | 增加“应用场景”“实践任务”“面试追问”。 |
| 掌握度较高 | 减少定义解释，增加迁移、边界条件和进阶关联。 |

资源详情里的 `generation_basis_json.personalization` 可记录画像使用摘要，但正文中不要暴露完整画像字段。

## 6. 多智能体流程

推荐流程：

```text
IntentAgent
  -> 识别 mindmap 资源类型、目标知识点、难度和约束
ProfileAgent
  -> 读取画像、掌握度和近期对话
RetrieverAgent
  -> need_course_evidence 为 true 且有课程时检索课程资料
MindmapPlannerAgent
  -> 规划根节点、二级分支和个性化分支
VisualAgent
  -> 生成 Mermaid JSON 外壳
VerifyAgent
  -> 校验 JSON 字段、Mermaid mindmap 语法、层级、覆盖、引用、难度和可视化可读性
SafetyAgent
  -> 安全、版权和不当内容审查
SaveNode
  -> 保存 Resource、ResourceVersion、引用和画像快照
```

现有后端可以先不新增真实类，通过 `ResourceRepository` 的节点函数承载这些角色；但任务步骤文案建议针对 `mindmap` 做更精确显示：

```text
课程检索 Agent
画像 Agent
导图规划 Agent
结构生成 Agent
引用核验 Agent
安全审查 Agent
保存节点
```

## 7. Prompt 设计

`backend/app/services/resource/prompts.py` 中 `mindmap` schema 建议升级为：

```text
正文结构（Mermaid 思维导图 JSON 外壳）：
- 只输出 JSON，不输出 Markdown、HTML、表格或解释文字。
- chart_type 固定为 mindmap，syntax 固定为 mermaid。
- source_code 第一行固定为 mindmap，第二行使用 root((知识点名称))。
- 只使用 root、主要分支、短节点说明三层。
- 主要分支必须覆盖：定义、前置、关键步骤、常见误区、练习、与后续章节关系。
- 根据学生画像增删一个个性化分支，例如代码视角、公式位置、项目应用或面试追问。
- 每个节点使用短句，避免长段落和 Mermaid 易冲突字符。
- 不要逐条复制课程引用材料，不要输出检索过程。
```

如果 `difficulty = basic`，prompt 应要求增加“前置知识”和“学习步骤”。如果 `difficulty = advanced`，prompt 应要求增加“边界条件”“迁移应用”或“后续章节关系”。

## 8. 质量核验

VerifyAgent 对思维导图增加专用检查：

* 是否是合法 JSON 对象，且只包含 `chart_type`、`syntax`、`source_code`。
* `source_code` 是否通过 Mermaid mindmap 基础语法校验。
* 是否至少有 5 个主要分支。
* 是否不存在 Markdown 代码围栏、表格或 HTML。
* 是否未输出内部 prompt、画像原文、检索过程。
* 是否覆盖目标知识点的定义、结构、误区、练习和后续关联。
* 是否与 `difficulty` 匹配。
* 是否体现画像中的关键偏好或薄弱点。
* 如果 `need_course_evidence = true`，是否有引用元信息或明确标记引用不足。
* 是否适合 Mermaid 渲染：节点短、层级稳定、分支不过度膨胀。

建议后续新增轻量函数：

```python
def validate_mermaid_mindmap_source(source_code: str) -> dict[str, object]:
    """校验 Mermaid mindmap 源码是否满足知识思维导图资源格式。"""
```

该函数可返回 `passed`、`warnings`、`branch_count`、`max_depth`，并并入 `quality_check_result`。

## 9. 前端落点

当前前端落点：

* `frontend/src/config/chat-commands.ts` 已包含“知识思维导图”资源生成命令，`resourceType: 'mindmap'`。
* `frontend/src/types/index.ts` 已包含 `mindmap` 资源类型。
* `ArtifactCanvas` 在 `resourceType === 'mindmap'` 时进入专用导图预览面板，默认用 Mermaid 渲染 SVG 知识导图，并保留 Mermaid 源码视图。
* 导图预览优先解析 JSON 外壳中的 `source_code`；旧版 `# / ## / ###` Markdown 导图作为兼容兜底继续可预览。引用信息仍进入右侧引用面板或任务元信息，不写入导图正文。
* ResourceTaskCard 展示类型时使用“思维导图”，不要直接展示 `mindmap`。
* 导出能力支持 Mermaid 源码、SVG 和 PNG；SVG / PNG 可从导图面板或 ArtifactCanvas 顶部更多菜单触发。

## 10. 失败与改写

失败策略与资源生成统一，但思维导图应增加结构类错误提示：

| 场景 | 处理 |
|---|---|
| 模型输出不是 Mermaid JSON 外壳 | 将 Pydantic 或 Mermaid 校验错误回传模型修复；连续失败后标记格式核验失败。 |
| 分支过少 | 要求补齐定义、前置、结构、误区、练习、关联。 |
| 分支过长 | 要求压缩为短节点，避免长段落。 |
| 引用不足 | 标记引用不足，允许重新检索或普通生成。 |
| 用户要求局部改写 | 保持根节点和主分支稳定，只改目标分支。 |

常见改写指令：

* “降到零基础版本”
* “加一个代码实践分支”
* “把公式推导讲清楚”
* “删除太细的节点”
* “改成考前复习导图”
* “基于课件重新生成并带引用”

## 11. 验收标准

1. 用户可通过资源生成入口选择“知识思维导图”。
2. 请求体使用 `action_type = "resource_generation"` 和 `resource_type = "mindmap"`。
3. 有课程时默认绑定 `course_id / concept_id / path_node_id`。
4. 选择基于课件生成时，先检索课程资料，再由 ChatProvider 生成导图正文。
5. 生成过程通过 ResourceTaskCard 展示，并可打开 ArtifactCanvas。
6. ArtifactCanvas 对 `mindmap` 展示专用导图预览，支持导图视图和 Mermaid 源码视图切换。
7. 正文为 Mermaid JSON 外壳，`source_code` 通过 Mermaid mindmap 基础语法校验。
8. 导图体现学生画像或掌握度差异。
9. 引用信息进入右侧引用面板或任务元信息，不污染导图正文。
10. 保存后生成 ResourceVersion，支持编辑、恢复、提交审核和进入资源大厅。
11. 导图支持 Mermaid 源码、SVG 和 PNG 导出。
12. 生成失败时有明确错误状态和重试入口，不使用本地伪造模板兜底。
