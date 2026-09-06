# 多智能体资源生成设计

## 1. 设计目标

资源生成是系统区别于普通 AI 聊天工具的重要能力。它不是简单让模型回复一段文本，而是围绕用户画像、课程上下文、学习路径节点、课程资料依据和资源生命周期，生成可预览、可编辑、可保存、可审核、可复用的学习资源。

设计目标：

1. 支持至少 5 类个性化资源生成。
2. 支持有课程和无课程两种生成场景。
3. 支持按需基于课程资料生成并展示引用来源。
4. 支持多智能体协作完成规划、检索、生成、核验、改写和安全审查。
5. 资源生成过程通过 ResourceTaskCard 和 ArtifactCanvas 可视化。
6. 生成结果可以进入资源大厅或资源审核流程。

---

## 2. 资源类型

系统至少支持以下资源类型：

| 资源类型 | 说明 | 是否可课程绑定 |
|---|---|---|
| 高白话讲义 | 将复杂知识点转成分层、易懂、带例子的讲义 | 是 |
| 专业课程讲解文档 | 面向课程章节的系统性讲解文档 | 是 |
| 知识点思维导图 | 以结构化层级展示知识关系 | 是 |
| 阶段测评题 | 选择题、填空题、简答题、代码题等 | 是 |
| 错题补救卡 | 针对易错点生成原因分析和补救练习 | 是 |
| PyTorch / 代码实操案例 | 代码类实验、运行步骤、讲解和扩展任务 | 是 |
| 拓展阅读包 | 延伸阅读、论文、概念背景、学习建议 | 可选 |
| PPT 大纲 | 用于课堂展示或自学汇报的结构化大纲 | 可选 |
| 视频 / 动画脚本 | 多模态讲解脚本、分镜、旁白、画面描述 | 可选 |
| 实践项目材料 | 小项目任务书、步骤、验收标准、扩展方向 | 可选 |

---

## 3. 生成场景

### 3.1 有课程资源生成

用户选择课程后触发资源生成。

如果用户从学习路径的章节节点点击“生成高白话讲义 / 梳理思维导图 / 开启 5 分钟通关测”等入口，前端只通过 URL 携带 `type`、`concept`、`path_node` 和资料范围等结构化上下文，不再把完整提示词放入地址栏。AI 对话舱根据这些上下文在本地生成可编辑草稿并选中资源类型；该入口只做上下文补全和资源类型选中，不应绕过用户确认直接创建任务。

```text
全局画像
+ 当前课程画像
+ 当前课程上下文
+ 当前知识点 / 路径节点
+ 用户本轮需求
+ 可选课程资料依据
  ↓
ResourceAgent 生成资源
```

生成结果默认绑定：

* `courseId`；
* `conceptId`；
* `pathNodeId`；
* `resourceType`；
* `profileContextSnapshot`。

### 3.2 无课程通用资源生成

用户未选择课程时，也可以生成资源。

```text
全局画像
+ 当前会话主题
+ 用户本轮需求
  ↓
ResourceAgent 生成通用资源
```

生成结果默认：

* `scope = general`；
* `courseId = null`；
* 可后续手动归档到课程；
* 不写入课程资源池，除非用户选择关联课程。

### 3.3 默认尝试课程资料依据的资源生成

用户在课程内触发资源生成时，系统默认尝试调用 CloudRagProvider 获取课程资料依据；如果命中可靠依据，就带引用交给 ChatProvider 生成资源正文；如果课程资料不可用或未命中可靠片段，则自动降级为基于课程上下文和大模型直接生成，禁止展示模拟引用。

```text
用户选择资源类型
  ↓
ResourceAgent 判断 needCourseEvidence = true
  ↓
CloudRagProvider 尝试获取课程资料依据
  ↓
命中依据：ChatProvider 基于依据生成资源正文
未命中依据：ChatProvider 基于课程上下文直接生成资源正文
  ↓
VerifyAgent 核验引用覆盖
  ↓
ArtifactCanvas 展示资源、引用、版本和生成过程
```

如果课程资料不可用或未命中可靠片段，任务不失败，检索节点应记录：

```text
未命中可用课程资料依据，已改用课程上下文和大模型直接生成，不返回模拟引用。
```

---

## 4. 多智能体协作角色

资源生成建议采用多角色智能体协作。

| 智能体 | 职责 |
|---|---|
| IntentAgent | 识别用户要生成的资源类型、目标、难度、格式和约束。 |
| ProfileAgent | 读取有效画像上下文，决定资源难度、讲解风格和推荐形式。 |
| PlannerAgent | 生成资源大纲、章节结构、题型结构或项目步骤。 |
| RetrieverAgent | 在需要课程依据时调用 CloudRagProvider 获取课程资料片段。 |
| WriterAgent | 生成资源正文。 |
| ExerciseAgent | 生成题目、答案、解析、评分标准和变式练习。 |
| CodeAgent | 生成代码实验、注释、运行步骤、错误排查和扩展任务。 |
| VisualAgent | 生成思维导图、视频脚本、动画分镜或图解结构。 |
| VerifyAgent | 核验引用覆盖、内容完整性、难度匹配和格式要求。 |
| SafetyAgent | 做安全审查、版权风险、敏感内容和不当内容过滤。 |
| RewriteAgent | 根据用户反馈进行改写、降难度、扩写或转换格式。 |

并不是每次生成都需要全部智能体参与。系统根据 `resourceType` 和 `needCourseEvidence` 选择工作流。

---

## 5. 典型工作流

### 5.1 高白话讲义

```text
IntentAgent 识别讲义生成
  ↓
ProfileAgent 读取画像，确定讲解深度
  ↓
PlannerAgent 生成讲义大纲
  ↓
RetrieverAgent 可选获取课程资料依据
  ↓
WriterAgent 生成讲义正文
  ↓
VerifyAgent 检查是否覆盖核心概念
  ↓
SafetyAgent 审查
  ↓
ArtifactCanvas 展示
```

### 5.2 阶段测评题

阶段测评题采用 `docs/04-ai-orchestration-design.md` 中定义的生产级结构化输出治理链路，避免模型随意输出导致题单不可评分：

* 提示词约束：ExerciseAgent 使用完整 JSON 示例、字段说明、输出禁令和低温度，要求题目、选项、标准答案、解析、评分要点和关键词齐全；
* API 格式约束：生成端调用模型网关时启用 JSON mode、`response_format`、JSON Schema 或等价结构化输出能力，优先约束为后端可校验的题单 schema；
* 后端代码校验：服务端清洗模型输出后执行 JSON 解析、题型配比、字段类型、A-D 选项、客观题答案和主观题评分要点校验，校验通过后再渲染为前端可作答 Markdown；
* 输出修复层：校验失败时，将具体错误信息回传给模型，要求其重新输出满足契约的纯 JSON，而不是盲目重试；
* 标准化失败与降级：模型返回半结构化内容时，后端先将可用题干、选项和解析规范化为 `ai_repaired_quiz`；连续修复失败后才返回服务端标准化兜底题单，并在前端提示“AI 题单未通过质量校验，当前展示系统保底题单”，不把不可评分题单交给学生端。

接入讯飞星火 HTTP OpenAI 兼容接口时，生成端必须同时设置 `response_format: {"type": "json_object"}` 和消息内 JSON 指令。由于 Lite 等版本对 `system` 消息的能力支持弱于 Max / Ultra，阶段测评题的完整 JSON 示例、字段说明和输出禁令必须写入 `user` 消息，不能只依赖 `system` 角色提示。

客观题标准答案必须在生成阶段由 AI 返回；主观题必须提供参考答案、评分要点和关键词，学生提交后由评测服务同步调用 AI Rubric 评分，并与客观题自动判分一起写入测评、掌握度和画像证据。

```text
IntentAgent 识别测评题生成
  ↓
ProfileAgent 获取掌握度和易错点
  ↓
PlannerAgent 设计题型结构和难度分布
  ↓
ExerciseAgent 生成题目、答案、解析
  ↓
VerifyAgent 检查答案正确性和知识点覆盖
  ↓
ArtifactCanvas 展示题库
```

### 5.3 错题补救卡

```text
读取 Assessment / 错题归因
  ↓
ProfileAgent 提取易错点
  ↓
PlannerAgent 设计补救路径
  ↓
WriterAgent 生成原因解释
  ↓
ExerciseAgent 生成针对性练习
  ↓
VerifyAgent 检查是否对应错因
  ↓
ArtifactCanvas 展示补救卡
```

### 5.4 代码实操案例

```text
IntentAgent 识别代码实验
  ↓
ProfileAgent 判断代码基础
  ↓
PlannerAgent 设计实验目标和步骤
  ↓
CodeAgent 生成代码、注释和运行说明
  ↓
VerifyAgent 检查代码逻辑与依赖
  ↓
WriterAgent 补充原理解释
  ↓
ArtifactCanvas 展示代码实验
```

### 5.5 视频 / 动画脚本

```text
IntentAgent 识别多模态脚本
  ↓
ProfileAgent 判断用户偏好
  ↓
VisualAgent 生成分镜结构
  ↓
WriterAgent 生成旁白和画面说明
  ↓
VerifyAgent 检查逻辑顺序
  ↓
ArtifactCanvas 展示脚本
```

---

## 6. ResourceTaskCard

ResourceTaskCard 是资源生成任务在 AI 对话舱中的可视化载体。

### 6.1 展示字段

* 资源标题；
* 资源类型；
* 绑定范围：课程 / 通用；
* 关联课程；
* 关联知识点；
* 是否基于课程资料；
* 任务状态；
* 生成进度；
* 引用覆盖状态；
* 当前智能体阶段；
* 打开预览；
* 查看生成过程；
* 重试；
* 失败原因。

### 6.2 状态枚举

```ts
export type ResourceTaskStatus =
  | 'queued'
  | 'planning'
  | 'retrieving'
  | 'generating'
  | 'verifying'
  | 'safety_checking'
  | 'completed'
  | 'failed'
  | 'cancelled'
```

### 6.3 设计原则

* 用户消息只展示用户自然语言；
* AI 方消息展示 ResourceTaskCard；
* 课程资料问答不创建 ResourceTaskCard；
* 资源生成任务必须有可追踪状态；
* 点击“打开预览”进入 ArtifactCanvas；
* 失败时给出明确原因和重试入口。

---

## 7. ArtifactCanvas

ArtifactCanvas 是资源生成、预览、编辑和保存的主画布。

### 7.1 功能

* 展示资源生成进度；
* 展示资源大纲；
* 展示资源正文；
* 展示引用来源；
* 展示生成过程和智能体 trace；
* 支持编辑；
* 支持保存；
* 支持 Markdown、DOCX、PPTX、本地打印 PDF 导出；
* 支持思维导图 SVG / PNG 导出和图解包单图下载；
* 支持重新生成；
* 支持局部改写；
* 支持版本恢复；
* 支持提交资源大厅或审核；
* 支持通用资源归档到课程。

### 7.2 画布结构

```text
ArtifactCanvas
  ├─ 顶部工具栏
  │    ├─ 资源标题
  │    ├─ 资源类型
  │    ├─ 绑定范围
  │    ├─ 保存 / 提交 / 导出
  │
  ├─ 左侧资源目录 / outline
  ├─ 中间正文预览 / 编辑区
  ├─ 右侧元信息
  │    ├─ 引用来源
  │    ├─ 画像使用说明
  │    ├─ 版本记录
  │    └─ 生成 trace / 多智能体工作流
```

### 7.3 导出与生成过程可视化

ArtifactCanvas 的导出能力在前端本地完成，不新增后端导出端点。DOCX 使用 `docx` 生成原生文档，PPTX 使用 `pptxgenjs` 生成原生演示文稿，两类导出库在用户触发导出时按需加载，不再维护手写 OOXML 模板。当前支持：

* Markdown 下载；
* DOCX 原生文档导出；
* PPTX 原生演示文稿导出；
* 浏览器打印 / 另存 PDF；
* 思维导图资源的 SVG / PNG 导出；
* 图解包中的单图下载。

Inspector 的“生成过程”页需要同时展示两层信息：

* 多智能体工作流概览：按规划、取证、生成、核验、安全、保存聚合后端 `steps.phase`，无独立节点时显示等待或跳过，不伪造完成状态；
* Trace 时间线：展示后端返回的原始步骤、状态、细节和异常信息，便于用户和管理员追踪失败原因。

### 7.4 画像提示

资源详情中可以轻量提示：

```text
已根据你的学习画像调整难度：偏代码实践型，当前知识点掌握度中等，已增加示例和练习。
```

不要把完整画像字段塞入资源正文。

---

## 8. 资源数据模型

### 8.1 ResourceTask

```ts
interface ResourceTask {
  id: string
  userId: string
  scope: 'course' | 'general'
  courseId?: string | null
  conceptId?: string | null
  pathNodeId?: string | null
  resourceType: ResourceType
  prompt: string
  status: ResourceTaskStatus
  progress: number
  needCourseEvidence: boolean
  profileContextSnapshotId?: string
  artifactId?: string
  errorCode?: string
  errorMessage?: string
  createdAt: string
  updatedAt: string
}
```

### 8.1.1 ResourceGenerationStep

```ts
interface ResourceGenerationStep {
  name: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | string
  detail?: string | null
  phase?: 'planning' | 'retrieving' | 'generating' | 'verifying' | 'safety_checking' | 'completed' | string | null
  citations?: Citation[]
}
```

`phase` 用于前端 Inspector 将原始步骤聚合为规划、取证、生成、核验、安全、保存六类工作流节点；没有 `phase` 时，前端只能按步骤名称做兜底归类。

### 8.2 Artifact

```ts
interface Artifact {
  id: string
  taskId: string
  userId: string
  scope: 'course' | 'general'
  courseId?: string | null
  title: string
  resourceType: ResourceType
  outline?: ArtifactOutline
  content: string
  citations?: Citation[]
  version: number
  status: 'draft' | 'saved' | 'submitted' | 'approved' | 'rejected'
  createdAt: string
  updatedAt: string
}
```

### 8.3 Citation

```ts
interface Citation {
  id: string
  documentId: string
  documentTitle: string
  page?: number
  chunkId?: string
  quote?: string
  providerId: string
  confidence?: number
}
```

---

## 9. 资源生命周期

```text
用户触发资源生成
  ↓
创建 ResourceTask
  ↓
AI 方消息展示 ResourceTaskCard
  ↓
多智能体生成资源
  ↓
ArtifactCanvas 预览
  ↓
用户编辑 / 改写 / 保存
  ↓
保存为个人资源
  ↓
可选择提交资源大厅 / 社区审核
  ↓
管理员资源审核
  ↓
审核通过进入可复用资源池
  ↓
资源大厅聚合接口展示为社区 / 精选 / 推荐资源，并返回结构化推荐证据
```

资源提交审核后，前端应进入真实后端闭环：

* `POST /api/v1/resources/{resource_id}/submit-community` 创建或更新 `pending_review` 审核记录；
* `/admin/resource-review` 从后端审核队列读取待审资源；
* 审核通过或精选后，资源大厅通过 `/api/v1/resources/hall` 展示该资源；
* 资源大厅卡片和详情展示 `recommendation_evidence`，解释课程匹配、画像匹配、薄弱点、掌握度短板、最近学习事件、引用和质量复用依据；
* 驳回、要求修改、隐藏或归档后，资源大厅应按审核状态隐藏或降低可见性；
* 卡片统计、详情正文、引用、版本和审核状态必须来自后端，不能使用前端本地演示值。

通用资源可在保存后选择：

```text
归档到课程
  ↓
选择 courseId / conceptId / pathNodeId
  ↓
变为课程资源
```

---

## 10. 与画像联动

资源生成必须读取有效画像上下文。

| 画像信息 | 影响资源生成 |
|---|---|
| 专业背景 | 选择案例领域和术语密度。 |
| 认知风格 | 决定图解、代码、公式、类比的比例。 |
| 知识基础 | 决定讲义深度和前置解释。 |
| 易错点 | 决定练习重点和补救内容。 |
| 学习目标 | 决定资源偏应试、项目、科研还是求职。 |
| 学习节奏 | 决定资源长度和任务拆分。 |
| 资源偏好 | 决定推荐生成类型和输出格式。 |
| 迁移能力 | 决定是否加入变式题和项目任务。 |

---

## 11. 质量核验

VerifyAgent 需要检查：

* 是否满足资源类型格式；
* 是否覆盖目标知识点；
* 是否与用户画像匹配；
* 是否存在明显事实错误；
* 题目答案是否一致；
* 代码是否有基本语法和依赖说明；
* 基于课程资料生成时是否有引用；
* 引用是否覆盖关键内容；
* 是否存在内容过浅或过难的问题。

---

## 12. 失败处理

常见失败场景：

| 失败场景 | 处理方式 |
|---|---|
| ChatProvider 未配置 | 资源生成按钮置灰或提示配置 Chat 模型。 |
| CloudRAG 未配置 | 基于课件生成不可用，可切换普通生成。 |
| 课程资料未向量化 | 提示等待处理完成或普通生成。 |
| 引用不足 | 标记引用不足，允许重新检索或普通生成。 |
| 生成超时 | ResourceTaskCard 显示失败和重试。 |
| 安全审查不通过 | 展示安全拦截提示，不保存资源正文。 |

---

### 12.1 无 Redis 本地演示运行

生产环境建议使用 Valkey/Redis 驱动任务队列和进度 pub/sub。本地未安装 Redis 时按以下方式降级运行：

* `VALKEY_URL` 可以留空；入队接口会安全降级，任务仍会落库为 `queued`，不会因无效 Redis URL 返回 500。
* `RESOURCE_GENERATION_WORKER_ENABLED=true` 时，进程内调度器会从数据库兜底认领最早可执行任务。
* 数据库兜底路径完成认领后直接进入流水线，禁止二次认领，否则新租约会被当前 worker 自己的锁拒绝，任务卡在 `planning`。
* 数据库兜底会回收租约已过期的中间状态任务，避免 worker 异常退出后任务永久滞留。
* 未配置 Redis 时，任务进度 WebSocket 会自动退回数据库轮询，前端仍可看到阶段进度。

---

## 13. 验收标准

1. 系统至少支持 5 类个性化资源生成。
2. 资源生成必须通过 ResourceTaskCard 展示任务状态。
3. 点击任务卡片可以打开 ArtifactCanvas。
4. ArtifactCanvas 支持预览、编辑、保存和提交。
5. 已选课程时资源默认绑定课程上下文。
6. 未选课程时资源可以作为通用资源生成，并可后续归档到课程。
7. 基于课程资料生成时必须展示引用或引用不足提示。
8. 资源生成必须读取有效画像上下文。
9. 资源生成失败时必须有明确错误状态和重试入口。
10. 资源可以进入资源大厅或资源审核流程。
11. 提交审核、审核通过、精选、驳回、隐藏和归档后，资源大厅与资源审核页的数据必须同步刷新。
12. 资源画布支持 Markdown、DOCX、PPTX 和浏览器打印 / 另存 PDF 导出，DOCX / PPTX 由前端成熟生成库完成，不依赖手写 OOXML。
13. 思维导图资源在 ArtifactCanvas 中支持导图预览、Markdown 源码查看，以及 Markdown / SVG / PNG 导出。
14. Inspector 的生成过程页能按规划、取证、生成、核验、安全、保存展示多智能体工作流概览，并保留原始 Trace 时间线。
