# API、数据模型与验收标准

## 1. 文档定位

本文用于统一说明智课未来的 API 契约、核心数据模型、状态流转和测试验收要求。前序文档已经分别描述页面、画像、AI 编排、资源生成和管理端能力，本文只关注以下问题：

* 用户侧页面如何调用后端；
* 管理端如何治理课程资料、模型网关和资源审核；
* ChatProvider 与 CloudRagProvider 的接口边界如何落到请求参数；
* 资源生成、课程资料问答、画像和运维日志依赖哪些核心数据；
* 软件杯项目验收时应如何验证功能闭环。

设计原则：

1. `/dashboard` 默认输入走普通 Chat，不默认调用课程资料问答。
2. 课程资料问答必须由用户显式选择，并且必须绑定课程和可用知识库。
3. 资源生成必须经过 ResourceAgent + ChatProvider；需要课程依据时，先由 CloudRagProvider 检索，再由 ChatProvider 生成正文。
4. Adapter 只负责厂商协议适配，不负责业务意图判断。
5. 所有 AI 调用、资源任务、管理端关键操作都必须可追踪、可审计、可失败恢复。
6. 机器消费的大模型输出和工具调用必须遵循“提示词约束 + API 格式约束 + 后端校验 + 输出修复 / 重试 + 标准化降级”的纵深防御链路；校验通过前不得写入长期状态或执行真实副作用。
7. API 字段对外可以兼容 camelCase，服务端内部优先使用 snake_case。

---

## 2. 用户侧 API

### 2.0 认证、当前用户与课程选择

登录注册、当前用户资料和退出登录是所有用户侧能力的基础。

```http
POST  /api/v1/auth/register
POST  /api/v1/auth/login
GET   /api/v1/auth/me
PATCH /api/v1/auth/me
POST  /api/v1/auth/logout
GET   /api/v1/me/courses
GET   /api/v1/courses
GET   /api/v1/courses/with-knowledge
GET   /api/v1/courses/{course_id}
GET   /api/v1/me/current-course
PUT   /api/v1/me/current-course
GET   /api/v1/courses/{course_id}/concepts
```

关键行为：

* 注册需要邮箱、密码和显示名称；可选携带 `role` 字段（`student` 或 `ta`），默认为学生，用于登录后进入对应角色工作台。
* 登录成功后写入服务端会话令牌，`GET /auth/me` 用于恢复当前用户；前端仅在内存和 `sessionStorage` 保存当前会话 token，并会迁移清理旧版 `localStorage` token。
* `PATCH /auth/me` 当前只允许用户修改显示名称，不允许普通用户自行修改角色。
* `POST /auth/logout` 撤销当前令牌；没有令牌时仍返回幂等成功。
* WebSocket 连接不应把 token 放入 URL 查询参数；客户端应在收到 `auth_required` 后发送 `auth` 帧完成鉴权。
* 生产环境建议继续升级为 `HttpOnly + Secure + SameSite` Cookie 或短期 WebSocket 票据，避免长期 bearer token 暴露在前端可读存储中。
* 课程列表与当前课程接口决定学习路径、资源大厅、课程资料问答和画像的课程上下文。
* `GET /api/v1/courses/with-knowledge` 只返回当前用户可访问且已具备可检索知识库的课程；管理员可看到全部就绪课程，学生按有效选课记录过滤，`course_id` 返回稳定 UUID。

### 2.1 统一 AI 消息入口

普通学习对话、课程资料问答和从对话中触发资源生成，都可以通过统一入口提交。

```http
POST /api/v1/ai/messages
```

请求体：

```ts
interface AiMessageRequest {
  user_id?: string | null
  conversation_id?: string | null
  learning_scope?: 'general' | 'course'
  course_id?: string | null
  path_node_id?: string | null
  concept_id?: string | null
  message: string
  mode?: 'default_chat' | 'course_rag_qa'
  action_type?: 'chat' | 'resource_generation'
  resource_type?: ResourceType | null
  need_course_evidence?: boolean | null
  uploaded_doc_id?: string | null
  response_mode?: 'stream' | 'blocking'
  require_citations?: boolean | null
  auto_generate_resource?: boolean
  preferred_resource_type?: ResourceType | null
  intent_type?: 'DEFAULT_CHAT' | 'COURSE_RAG_QA' | 'KNOWLEDGE_QA' | 'RESOURCE_GENERATION' | 'GENERAL_CHAT'
  client_context?: Record<string, unknown>
  onboarding_history?: OnboardingHistoryMessage[]
  force_onboarding?: boolean
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `learning_scope` | `general` 表示无课程通用学习，`course` 表示课程内学习。未传时由 `course_id` 推断。 |
| `mode` | `default_chat` 调用 ChatProvider；`course_rag_qa` 调用课程资料问答链路。 |
| `action_type` | `chat` 为普通回答；`resource_generation` 表示本轮要创建资源生成任务。 |
| `resource_type` | 资源类型，例如 `lecture`、`quiz`、`mindmap`、`code_lab` 等。 |
| `need_course_evidence` | 资源生成是否先检索课程资料依据。 |
| `require_citations` | 课程资料问答或基于课件生成时是否强制要求引用。 |
| `client_context` | 前端状态快照，例如入口来源、选中节点、临时偏好，不替代服务端鉴权。多轮意图追问可传 `lastIntentRoute` / `intentHistory`。 |
| `onboarding_history` | 冷启动引导多轮历史快照，前端每轮持久化并回传，后端无状态重建引导上下文。 |
| `force_onboarding` | 强制走引导模式（`workflow.stream_chat`），用于 `/learning-profile` 页面"重塑学习画像"入口。别名 `forceOnboarding`。 |

响应体：

```ts
interface AiMessageResponse {
  conversation_id: string
  answer: string
  route: 'default_chat' | 'learning_progress' | 'course_rag_qa' | 'resource_generation'
  citations: Citation[]
  agent_trace: AgentTraceEvent[]
  suggested_actions: SuggestedAction[]
  quality?: ChatQuality | null
  availability?: AiAvailability | null
  resource_task_id?: string | null
}
```

#### 2.1.1 Hybrid Router 行为

`AiOrchestratorService` 在处理请求前会调用 `HybridIntentRouter`。HTTP 和 WebSocket 共用同一个路由器。

路由优先级：

```text
显式 mode / action_type / intent_type
  > client_context.lastIntentRoute 多轮上下文
  > 规则层
  > 可选 Embedding 语义分类
  > 本地小模型语义分类
  > 低置信度澄清或默认 Chat
```

典型识别：

| 用户问题 | 预期 route | 说明 |
|---|---|---|
| `我目前学到哪了` | `learning_progress` | 读取真实学习进度快照。 |
| `我的学习进度怎么样` | `learning_progress` | 读取掌握度、路径节点和薄弱点。 |
| `那下一步呢`，且上一轮为 `learning_progress` | `learning_progress` | 多轮追问。 |
| `课件里怎么定义梯度下降` | `course_rag_qa` | 课程资料问答。 |
| `解释一下梯度下降` | `default_chat` | 普通 ChatProvider。 |
| `根据我的薄弱点出五道练习题` | `resource_generation` | 创建资源生成任务。 |

低置信度时，接口返回普通回答形态的澄清问题：

```json
{
  "route": "default_chat",
  "availability": {
    "ok": true,
    "code": "intent_clarification_required"
  }
}
```

#### 2.1.2 WebSocket 引导模式分流

`/ws/ai/{conversation_id}` 在调用 `orchestrator.handle_message` 之前检测引导条件。命中则走 `workflow.stream_chat` 流式输出（含完整 onboarding 逻辑），否则保持原 `handle_message` 非流式路径：

```python
chat_request = payload.to_chat_request()
should_stream_onboarding = is_general_learning(chat_request) and (
    bool(chat_request.onboarding_history)
    or bool(getattr(chat_request, "force_onboarding", False))
    or OnboardingService(db).is_cold_start(current_user.id)
)
```

`stream_chat` 输出事件序列：

| 事件类型 | 说明 |
|---|---|
| `agent_trace` | 各节点执行轨迹（课程上下文、意图路由、安全审查、课程检索、回答生成等） |
| `session_started` | 会话 ID |
| `citation_update` | 课程检索引用 |
| `text_delta` | 引导模式下为 `user_visible` 分块打字机输出（非引导模式为原始 LLM delta） |
| `quality_update` | 引用与安全质量 |
| `profile_updated` | 画像证据记录 |
| `onboarding_update` | `{meta: {onboarding: OnboardingMetadata}}`，文本流结束后、done 前发送 |
| `path_updated` | 学习路径节点状态 |
| `suggested_actions` | 建议动作 |
| `done` | 终帧，含 `meta.onboarding`（与 `onboarding_update` 一致，作为前端兜底） |

> 关键：若 WebSocket 仅调用 `handle_message`（走 `run_chat`），则冷启动检测、LLM 结构化返回、`onboarding_update`、`done.meta.onboarding` 均不生效，引导模式完全不工作。引导模式必须走 `stream_chat`。

### 2.2 普通 Chat 调用

```json
{
  "learning_scope": "general",
  "message": "帮我解释一下反向传播",
  "mode": "default_chat",
  "action_type": "chat"
}
```

处理链路：

```text
前端输入
  ↓
AiOrchestratorService
  ↓
ProfileContextResolver
  ↓
ChatProvider
  ↓
返回 answer / suggested_actions / trace
```

约束：

* 无课程状态可用。
* 不创建 ResourceTaskCard。
* 不调用 CloudRagProvider。
* 可读取全局画像和会话画像调整回答深度。

### 2.2.1 意图路由反馈

路由反馈用于把人工纠错或前端反馈沉淀为后续评测样例。

```http
POST /api/v1/ai/router-feedback
```

请求体：

```ts
interface IntentRouterFeedbackRequest {
  trace_id?: string | null
  conversation_id?: string | null
  message: string
  predicted_intent: string
  expected_intent?: string | null
  is_correct: boolean
  comment?: string | null
}
```

写入日志：

```text
ModelCallLog.capability = intent_feedback
ModelCallLog.status = correct | incorrect
ModelCallLog.meta_json.predicted_intent / expected_intent / comment
```

### 2.3 课程资料问答调用

```json
{
  "learning_scope": "course",
  "course_id": "deep-learning-001",
  "message": "课件里卷积层输出尺寸是怎么计算的？",
  "mode": "course_rag_qa",
  "action_type": "chat",
  "require_citations": true
}
```

处理链路：

```text
用户显式选择“课程资料问答”
  ↓
校验 course_id、课程访问权限和当前 RAG 后端状态
  ↓
CloudRagProvider 检索；`RAG_BACKEND=local_pgvector` 时由本地 PGVector 混合检索
  ↓
返回 answer + citations
```

约束：

* 必须有 `course_id`。
* `iflytek_chatdoc` 模式必须有可用 CloudRagProvider；`local_pgvector` 模式必须有可检索本地文档和向量切片。
* `courses/{course_id}/ai-context` 会按后端返回 `knowledge_ready`、`file_ids_count`、`qa_mode` 和 `rag_backend`，前端据此启用或禁用课程资料问答。
* 不创建 ResourceTaskCard。
* 不打开 ArtifactCanvas。
* 若未命中文档，应根据课程绑定策略决定是否允许回退普通 Chat，并清晰提示引用不足。

### 2.4 资源生成任务

资源生成可以从 `/dashboard` 快捷命令、学习路径节点、资源工坊深链或 AI 建议动作触发。

```http
POST /api/v1/resource-tasks
POST /api/v1/resources/generate
GET  /api/v1/resources/tasks
GET  /api/v1/resources/tasks/{task_id}
POST /api/v1/resources/tasks/{task_id}/run
POST /api/v1/resources/tasks/{task_id}/cancel
PATCH /api/v1/resources/tasks/{task_id}/outline
```

`POST /api/v1/resource-tasks` 与 `POST /api/v1/resources/generate` 语义一致，均用于创建资源生成任务；前端推荐使用 `/resource-tasks`，历史页面可继续兼容 `/resources/generate`。

请求体：

```ts
interface ResourceGenerateRequest {
  scope: 'course' | 'general'
  course_id?: string | null
  concept_id?: string | null
  path_node_id?: string | null
  resource_type: ResourceType
  difficulty: 'basic' | 'medium' | 'advanced'
  goal: string
  requirements?: string | null
  topic?: string | null
  need_course_evidence: boolean
  action_type?: 'resource_generation' | null
  client_context?: Record<string, unknown> | null
}
```

响应体：

```ts
interface ResourceGenerationTask {
  task_id: string
  status: ResourceTaskStatus
  scope: 'course' | 'general'
  course_id?: string | null
  resource_type: ResourceType
  resource_type_label?: string | null
  difficulty: string
  progress: number
  current_agent?: string | null
  steps: ResourceGenerationStep[]
  draft_content?: string | null
  outline_json: OutlineSection[]
  citations: Citation[]
  need_course_evidence: boolean
  course_evidence_required: boolean
  citation_coverage?: 'passed' | 'insufficient' | 'missing' | 'skipped' | null
  result_resource_id?: string | null
  result_resource_code?: string | null
  error_code?: string | null
  error_message?: string | null
  error_root_cause?: string | null
  orchestration: Record<string, unknown>
}
```

`ResourceGenerationStep` 用于同时承载原始 Trace 时间线和前端工作流聚合：

```ts
interface ResourceGenerationStep {
  name: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | string
  detail?: string | null
  phase?: 'planning' | 'retrieving' | 'generating' | 'verifying' | 'safety_checking' | 'completed' | string | null
  citations?: Citation[]
}
```

前端 Inspector 使用 `phase` 将步骤聚合为规划、取证、生成、核验、安全、保存节点；无独立节点时只显示等待或跳过，不伪造已完成状态。

幂等要求：

* 创建任务接口支持 `X-Idempotency-Key`。
* 同一用户同一幂等键重复提交时，应返回已创建的任务，不重复扣减配额，不重复入队。
* 幂等缓存不得跨用户共享。

任务状态：

```ts
type ResourceTaskStatus =
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

### 2.5 资源与版本

```http
GET  /api/v1/resources
GET  /api/v1/resources/hall
GET  /api/v1/resources/community/list
GET  /api/v1/resources/{resource_id}
PUT  /api/v1/resources/{resource_id}
GET  /api/v1/resources/{resource_id}/versions
POST /api/v1/resources/{resource_id}/versions/{version}/restore
POST /api/v1/resources/{resource_id}/copy
POST /api/v1/resources/{resource_id}/submit-community
POST /api/v1/resources/{resource_id}/archive-course
POST /api/v1/resources/upload
POST /api/v1/resources/assets/references
GET  /api/v1/resources/assets/{asset_id}/file
DELETE /api/v1/resources/{resource_id}
DELETE /api/v1/resources/batch
```

关键行为：

* `GET /resources` 用于个人资源和课程资源列表，必须鉴权；私有、待审核和生成中的资源只返回当前创建者自己的数据，审核通过的 `published` / `featured` 资源才可作为共享资源返回。
* `GET /resources/hall` 用于资源大厅聚合视图，返回真实列表、统计、筛选项、高亮区和分页；聚合可见性必须遵循“本人资源 + 公开资源”，不得因为处于同一课程而展示其他用户私有资源。
* `GET /resources/community/list` 用于兼容社区资源检索，必须只返回公开社区资源，并在传入课程时校验当前用户课程访问权限。
* `GET /resources/{resource_id}` 与 `GET /resources/{resource_id}/versions` 必须鉴权；私有资源正文和历史版本只允许创建者本人或管理员读取。
* `PUT /resources/{resource_id}` 用于 ArtifactCanvas 保存标题、摘要、正文、难度和状态。
* `versions` 用于版本恢复，恢复后应产生新的可展示版本状态。
* `submit-community` 将个人资源提交到审核队列，状态进入 `pending_review`。
* `archive-course` 仅允许把通用资源归档到用户有访问权限的课程。
* `upload` 支持 Markdown/TXT 文件或粘贴正文创建个人资源，并可选择直接提交审核。
* `assets/references` 支持上传资源生成参考图，文件访问必须校验课程、公开资源或资源所有权。
* 删除个人资源后，资源大厅、推荐列表和审核队列必须同步移除或归档相关记录。

资源大厅查询参数：

| 参数 | 说明 |
|---|---|
| `course_id` | 当前课程上下文，可为空。 |
| `q` | 搜索标题、摘要、知识点、推荐理由和结构化推荐证据等文本。 |
| `scope` | `all`、`course`、`general`、`mine`、`community`、`recommended`。 |
| `type` | 资源类型过滤。 |
| `difficulty` | 难度过滤。 |
| `page` | 页码，从 1 开始。 |
| `page_size` | 每页数量，范围 6 到 48。 |

资源大厅响应体：

```ts
interface ResourceHallResponse {
  items: Resource[]
  stats: {
    total: number
    course: number
    general: number
    mine: number
    community: number
    recommended: number
    featured: number
    with_citations: number
    avg_quality: number
    total_views: number
    total_copies: number
  }
  filters: {
    scopes: ResourceHallFilterOption[]
    resource_types: ResourceHallFilterOption[]
    difficulties: ResourceHallFilterOption[]
  }
  highlights: {
    featured: Resource[]
    recommended: Resource[]
    recent: Resource[]
  }
  pagination: {
    page: number
    page_size: number
    total_items: number
    total_pages: number
    offset: number
    has_prev: boolean
    has_next: boolean
  }
  course_id?: string | null
  query?: string | null
  generated_at: string
}
```

一致性要求：

* 资源大厅卡片、统计、筛选项、分页和详情必须来自后端返回数据。
* 卡片展示的浏览数、复制数、引用数量、质量分、推荐证据、精选状态和审核状态应与 `GET /resources/{resource_id}` 详情一致。
* 详情弹层正文必须按 Markdown 渲染为标题、列表、表格、代码块等可读格式；模型返回的外层代码围栏或裸 `markdown` 语言标记不得直接暴露给学生端。
* 审核通过或精选后资源可进入 `community` / `featured` 范围；驳回、隐藏、归档资源不得进入公开资源流。

### 2.6 学情画像读取与纠偏

```http
GET  /api/v1/learning-profile
POST /api/v1/learning-profile/corrections
POST /api/v1/learning-profile/onboarding/submit-chip
```

查询参数：

| 参数 | 说明 |
|---|---|
| `scope` | `all`、`global`、`course`、`session`、`cross_course` 等画像范围。 |
| `course_id` | 读取课程画像时传入。 |
| `conversation_id` | 读取当前会话画像时传入。 |

纠偏要求：

* 用户纠偏写入 `sourceType = 'user_correction'` 的证据。
* 用户纠偏优先级高于系统推断。
* 已纠偏维度不应被旧证据再次覆盖。

预设 chip 直写要求（`/onboarding/submit-chip`）：

* 冷启动引导中用户点击预设 chip 时走该接口，不调用 LLM，后端直接写入 `ProfileDimension`。
* `chip.category` 作为维度 key，`chip.value`（不填回退 `chip.label`）作为写入 label，置信度固定 0.88，证据来源标记为 `preset_chip`。
* 响应体 `aiReply` 为模板话术（前端用打字机效果展示），`meta` 复用 `OnboardingMetadata` 结构，含下一轮 `suggestedChips`、`currentDimensions`、`round`、`done`。
* 自由输入路径仍走 LLM 对话管道，不受该接口影响。

### 2.7 会话历史

会话历史用于支持 `/dashboard` 和 `/ai-room` 的历史抽屉、会话恢复、重命名和删除。

```http
GET    /api/v1/conversations
GET    /api/v1/conversations/{conversation_id}/messages
PATCH  /api/v1/conversations/{conversation_id}
DELETE /api/v1/conversations/{conversation_id}
```

关键行为：

* 列表支持按课程、通用学习范围和时间排序。
* 会话消息必须保留 route、引用、资源任务和 trace 信息，便于恢复学习上下文。
* 删除会话只影响当前用户可见历史，不应删除资源、画像证据或审计日志。

### 2.8 公告中心

公告中心用于顶部未读角标、系统通知列表、重要公告确认和公告详情阅读。

```http
GET  /api/v1/announcements/summary
GET  /api/v1/announcements
GET  /api/v1/announcements/{announcement_id}
POST /api/v1/announcements/{announcement_id}/read
POST /api/v1/announcements/{announcement_id}/dismiss
POST /api/v1/announcements/read-all
```

查询参数：

| 参数 | 说明 |
|---|---|
| `category` | 公告分类，例如 `system`、`course`、`maintenance`。 |
| `priority` | `info`、`success`、`warning`、`critical`、`maintenance`。 |
| `display_type` | `top_bar`、`modal`、`page_card`、`toast`、`list_only`。 |
| `unread_only` | 仅返回未读公告。 |
| `limit` | 返回数量上限。 |

关键行为：

* 公告按 `audience_role`、状态、生效时间和过期时间过滤。
* `summary` 返回顶部条、弹窗、页面卡片和 Toast 候选公告。
* 用户已读和关闭状态只作用于当前用户。

### 2.9 公开站点设置

登录页和注册页在未登录状态下读取公开站点设置。

```http
GET /api/v1/settings/login-background
```

该接口只返回可公开展示的登录背景配置，不需要登录。媒体地址必须是站内路径或 `http(s)` 地址。

### 2.10 练习评估

练习评估用于 `/assessment` 的即时测评和异步提交。

```http
POST /api/v1/assessments/draft
POST /api/v1/assessments
POST /api/v1/assessments/submit
```

关键行为：

* `/assessments/draft` 为 `/assessment` 独立测评页生成可作答题单，必须走 AI 结构化 JSON 契约、后端校验和输出修复，不允许前端使用泛化占位题替代真实题目。
* 同步接口返回测评结果、总分、Rubric 分项评分、错题归因、掌握度影响和自然语言学习进度报告。
* 可作答阶段测评通过 `answer` 提交结构化 JSON，`kind` 为 `stage_assessment_submission`，其中包含题目、学生答案、标准答案、分值、解析和评分要点；提交来源可以是 `/assessment` 独立测评页，也可以是 ArtifactCanvas 中打开的 `resource_type = quiz` 阶段测评资源。
* `stage_assessment_submission` 会优先按题目标准答案、关键词和分值执行题目级评分；客观题按 AI 生成阶段返回的标准答案自动判分，主观题在提交后同步调用 AI Rubric 评分，并把单题快照写入 `AssessmentItem`，便于错题回看。
* 学生答题中不调用 AI 问答；评分完成后，前端再携带题目、学生答案、参考要点、得分和错因跳转到 AI 学习室进行解析。
* 异步提交接口返回排队状态，适合较长的批改或补救生成任务。
* 前端应使用幂等键避免重复提交同一次答题结果。
* `ASSESSMENT_LLM_RUBRIC_ENABLED=true` 时，评估器优先通过 ModelGateway ChatProvider 执行结构化 LLM Rubric 评分；主观题评分并发由 `ASSESSMENT_LLM_CONCURRENCY` 控制，默认 5；模型不可用或 JSON 不合法时，回退本地结构化 Rubric，不静默伪造 LLM 结果。

响应体新增字段：

```ts
interface AssessmentResult {
  id: string
  score: number
  mastery_delta: number
  feedback: string
  weak_reasons: string[]
  recommended_actions: string[]
  rubric: Array<{
    key: string
    label: string
    score: number
    weight: number
    evidence: string
    feedback: string
  }>
  scoring_method: 'stage_assessment_ai_rubric' | 'stage_assessment_rubric' | 'llm_rubric' | 'heuristic_rubric' | string
  progress_report?: string | null
}
```

### 2.11 学习日程

学习日程用于 `/calendar` 保存系统建议事项、手动学习安排和完成状态。日程事项按当前用户隔离，可绑定课程、知识点、路径节点、资源或公告来源。

```http
GET    /api/v1/learning-schedules
POST   /api/v1/learning-schedules
PATCH  /api/v1/learning-schedules/{item_id}
DELETE /api/v1/learning-schedules/{item_id}
```

查询参数：

| 参数 | 说明 |
|---|---|
| `course_id` | 可选，按当前课程过滤。 |
| `start_date` / `end_date` | 可选，按日期范围过滤，格式 `YYYY-MM-DD`。 |
| `status` | 可选，`planned`、`completed`、`skipped`。 |

关键行为：

* 保存系统建议事项后写入 `learning_schedule_items`。
* 标记完成或重新计划通过 `PATCH` 更新 `status`。
* 课程日程创建和完成会写入 `LearningEvent`，作为学习进度报告、画像证据和后续路径调整的上下文。
* 普通用户只能访问自己的日程。

### 2.12 用户侧课程资料

用户侧课程资料接口只暴露当前用户有权访问课程下的有效文档，用于学习路径资料范围切换、课程资料问答入口和原始教材预览。

```http
GET /api/v1/courses/{course_id}/documents
GET /api/v1/courses/{course_id}/documents/{document_id}/file
```

* 访问前必须通过登录态校验。
* 普通学生仅可访问已发布课程；访问时会沿用课程访问校验与学习关系记录。
* 原始文件预览必须校验 `document_id` 属于当前 `course_id`，且文档未删除。

### 2.13 学习路径、掌握度与课程画像

学习路径接口用于 `/learning-path` 和 `/calendar`。

```http
GET  /api/v1/courses/{course_id}/path
POST /api/v1/courses/{course_id}/path/generate
PUT  /api/v1/path-nodes/{node_id}/status
GET  /api/v1/path-nodes/{node_id}/mastery
GET  /api/v1/courses/{course_id}/mastery
GET  /api/v1/courses/{course_id}/profile
GET  /api/v1/courses/{course_id}/ai-context
GET  /api/v1/courses/{course_id}/extracted-qa
GET  /api/v1/courses/{course_id}/extracted-qa/{qa_id}
```

关键行为：

* 读取路径前必须校验用户有课程访问权限。
* `path/generate` 根据课程结构、知识点、画像和资料状态生成或刷新路径。
* 路径节点返回 `mastery` 和语义化别名 `mastery_score`；前端优先用 `mastery_score` 展示概念掌握度热力流。
* 节点状态更新用于标记开始、进行中、完成和补救状态，并影响掌握度；响应会返回最新 `mastery_score`。
* `/path-nodes/{node_id}/mastery` 返回单节点掌握度、状态、证据和更新时间，用于学习路径局部刷新。
* `mastery` 返回课程总掌握度、薄弱点和路径进度摘要。
* `ai-context` 为 AI 对话和资源生成提供课程上下文。
* `extracted-qa` 展示从课程资料萃取的问答和学习提示。

---

### 2.14 学习效果评估报告

学习效果评估报告用于 `/assessment/report` 聚合学习行为、画像、测验评分和资源使用数据，生成结构化评估报告，包含总体评分、维度评分和进步趋势。

```http
GET /api/v1/assessment/report?user_id={id}&course_id={id}
```

查询参数：

| 参数 | 说明 |
|---|---|
| `user_id` | 可选，目标用户 external_id；不传则默认当前登录用户。 |
| `course_id` | 可选，按课程过滤评估数据。 |

关键行为：

* 报告聚合 4 个数据源：`ProfileDimension`/`ConceptMastery`（知识掌握度）、`Assessment`（测验表现）、`LearningEvent`/`StudentLearningEvent`（学习参与度）、`Resource`（资源利用）。
* 4 个维度按权重（35%/30%/20%/15%）加权计算总体评分 0-100，并映射为优秀/良好/中等/待加强等级。
* 进步趋势按天聚合最近 4 周的测验评分，返回按时间顺序排列的数据点。
* 薄弱点来自画像维度中低于 60 分的掌握度指标，以及 ConceptMastery 中低于 60 分的知识点。
* 建议按薄弱点和低分维度自动生成，涵盖复习、练习、参与度和资源利用等方面。
* 普通用户只能查看自己的报告；查询他人报告需管理员或助教权限。

报告结构（`LearningReportResponse`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `user_id` | string | 用户 external_id |
| `course_id` | string? | 课程 ID |
| `course_title` | string? | 课程标题 |
| `overall_score` | int | 总体评分 0-100 |
| `overall_level` | string | 总体等级 |
| `dimensions` | ReportDimensionScore[] | 4 个维度评分 |
| `progress_trend` | ReportTrendPoint[] | 进步趋势数据点 |
| `weak_points` | string[] | 薄弱知识点/维度列表 |
| `recommendations` | string[] | 改进建议列表 |
| `assessment_count` | int | 参与测评次数 |
| `event_count` | int | 学习行为事件总数 |
| `generated_at` | datetime | 报告生成时间 |

验收标准：返回完整的评估报告 JSON，包含总体评分、至少 4 个维度评分和进步趋势数据。

---


### 2.15 学生端助教互动（班级、作业、测验、通知）

助教创建的班级、布置的作业与测验会同步到学生端，学生凭邀请码入班、在线作答、提交并接收助教提醒。所有接口要求登录用户为学生身份。

```http
GET    /api/v1/ta-student/classes
POST   /api/v1/ta-student/classes/join
DELETE /api/v1/ta-student/classes/{class_id}/leave
GET    /api/v1/ta-student/assignments
POST   /api/v1/ta-student/assignments/{assignment_id}/submit
GET    /api/v1/ta-student/quizzes
GET    /api/v1/ta-student/quizzes/{quiz_id}
POST   /api/v1/ta-student/quizzes/{quiz_id}/submit
GET    /api/v1/ta-student/notifications
POST   /api/v1/ta-student/notifications/{notification_id}/read
```

关键行为：

* 班级列表返回已加入班级的名称、教师姓名、邀请码、班内人数与入班时间。
* 学生凭 8 位邀请码加入班级；邀请码大小写不敏感，重复加入幂等返回，满员班级拒绝加入。
* 学生退出班级幂等，教师端可再次通过邀请码或其他方式将学生加入班级。
* 作业列表返回已发布作业及当前学生的提交状态（`submitted`、`attempt_number`、`submitted_at`、`score`）与题目数（`question_count`）。
* 作业提交：多题作业提交逐题作答（`answers`，客观题即时判分），单题作业提交文本（`answer`）；均支持重复提交，后端记录每次提交的 attempt_number 与提交时间。
* 测验/作业题目详情接口只返回题干、题型、选项与分值，不返回正确答案；客观题提交后即时判分并返回得分，含主观题的多题作业由 AI 批改后返回总分。
* 通知列表返回 `unread_count` 与逐条已读状态，标记已读幂等。

## 3. 管理侧 API

### 3.1 知识大本营

知识大本营只负责课程资料上传、解析、切分、向量化、检索测试和引用治理，不负责普通 Chat 或资源正文生成。

```http
GET  /api/v1/admin/knowledge/upload-policy
POST /api/v1/admin/courses/{course_id}/documents
GET  /api/v1/admin/knowledge/documents
GET  /api/v1/admin/courses/{course_id}/documents
GET  /api/v1/admin/documents/{document_id}/ingestion-status
GET  /api/v1/admin/documents/{document_id}/chatdoc-chunks
GET  /api/v1/admin/documents/{document_id}/native-chunks
POST /api/v1/admin/documents/{document_id}/native-chunks/sync
POST /api/v1/admin/documents/{document_id}/native-chunks/resplit
POST /api/v1/admin/documents/{document_id}/native-chunks/embed
GET  /api/v1/admin/knowledge/search
POST /api/v1/admin/knowledge/documents/batch-embed
POST /api/v1/admin/knowledge/documents/extract
GET  /api/v1/admin/knowledge/documents/recycled
POST /api/v1/admin/documents/{document_id}/restore
DELETE /api/v1/admin/documents/{document_id}
POST /api/v1/admin/documents/{document_id}/purge
```

文档处理状态：

| 状态 | 含义 | 用户侧影响 |
|---|---|---|
| `uploaded` | 已上传到系统或云端 | 还不能稳定问答 |
| `parsing` | 正在解析 | 课程资料问答不可用 |
| `chunking` | 正在切分 | 课程资料问答不可用 |
| `pending_activation` | 等待向量化激活 | 课程资料问答不可用 |
| `vectorizing` / `vectoring` | 正在向量化 | 课程资料问答不可用 |
| `ready` / `vectored` | 可检索 / 可问答 | 课程资料问答可用 |
| `failed` | 处理失败 | 用户侧提示不可用 |
| `deleted` | 已删除或进入回收站 | 不参与检索 |

### 3.2 模型网关

模型网关统一治理 Chat、Embedding、Vision、Doc QA 和 Resource Agent 调用能力，并通过调用日志承载 Intent Router 的路由记录与反馈记录。

```http
GET    /api/v1/admin/model-providers/templates
GET    /api/v1/admin/model-providers
POST   /api/v1/admin/model-providers
PUT    /api/v1/admin/model-providers/{provider_id}
DELETE /api/v1/admin/model-providers/{provider_id}
POST   /api/v1/admin/model-providers/{provider_id}/test
POST   /api/v1/admin/model-providers/test
POST   /api/v1/admin/model-providers/{provider_id}/default
POST   /api/v1/admin/model-providers/check-all
GET    /api/v1/admin/model-providers/health
GET    /api/v1/admin/model-providers/logs
DELETE /api/v1/admin/model-providers/logs
GET    /api/v1/admin/model-providers/traces/{trace_id}
GET    /api/v1/admin/model-providers/usage-stats
```

学生端个人模型覆盖：

```http
GET    /api/v1/me/model-override
PUT    /api/v1/me/model-override
DELETE /api/v1/me/model-override
POST   /api/v1/me/model-override/test
```

- 普通学生可读取、保存、删除和测试自己的聊天模型覆盖配置。
- 覆盖启用后，普通对话优先使用个人供应商；未启用时仍使用管理员在网关中心维护的默认模型。
- API Key 使用项目加密密钥托管，前端不回传已保存的明文密钥；测试接口只对传入的草稿配置进行连通性检测，不写数据库。

Intent Router 配置接口：

```http
GET  /api/v1/admin/intent-router/config
PUT  /api/v1/admin/intent-router/config
POST /api/v1/admin/intent-router/config/validate
POST /api/v1/admin/intent-router/config/evaluate
POST /api/v1/admin/intent-router/config/reload
POST /api/v1/admin/intent-router/config/publish
POST /api/v1/admin/intent-router/config/rollback
GET  /api/v1/admin/intent-router/config/export
POST /api/v1/admin/intent-router/config/import
```

`GET /api/v1/admin/intent-router/config` 至少返回：

```ts
interface IntentRouterConfigView {
  active_path: string
  active_version: string
  draft_version?: string | null
  updated_at?: string | null
  updated_by?: string | null
  validation: {
    ok: boolean
    errors: Array<{ path: string; message: string; line?: number; column?: number }>
  }
  evaluation?: {
    accuracy: number
    clarification_rate: number
    by_intent: Record<string, { precision: number; recall: number; false_positive: number; false_negative: number }>
  } | null
  yaml_text: string
}
```

供应商能力枚举：

```ts
type ModelProviderCapability =
  | 'chat'
  | 'embedding'
  | 'vision'
  | 'doc_qa'
  | 'resource_agent'
```

调用日志能力枚举：

```ts
type ModelCallLogCapability =
  | ModelProviderCapability
  | 'intent_route'
  | 'intent_feedback'
```

约束：

* ChatProvider 和 CloudRagProvider 必须分能力登记、分能力检测。
* 同一厂商可同时配置多类能力，但调用日志必须区分能力类型。
* API 密钥不得明文返回给前端，只能返回脱敏状态。
* ChatProvider 为 0 或默认 ChatProvider 不健康时，普通 Chat 与资源生成不可用。
* `intent_route` 和 `intent_feedback` 不代表模型供应商能力，只用于日志筛选、trace 复盘和路由优化。
* Intent Router 配置必须同时支持后台可视化编辑和直接编辑 YAML 文件。
* `reload` 必须从 `INTENT_ROUTER_REGISTRY_PATH` 指向的文件读取配置，校验通过后才能替换当前有效配置。
* `publish`、`rollback`、`reload`、`import`、`export` 必须写入 `AdminAuditLog`。
* Intent Router 配置文件不得包含 API Key、Secret、Token；云端 Embedding 和 LLM Judge 凭证仍由模型网关或环境变量管理。
* `semantic-router` 可用并返回候选时，`intent_route` 日志与候选 `source` 应体现云端 embedding 语义召回，不得退化为仅 `small_model`。

配置写入接口支持两种请求体：

```ts
interface IntentRouterConfigMutation {
  yaml_text?: string
  config?: IntentRouterRegistryConfig
}
```

`PUT /config` 仅保存草稿，不替换当前有效配置；`POST /config/publish` 可发布请求体中的配置，也可在无请求体时发布已保存草稿。`POST /config/import` 接收 YAML 文件并保存为草稿。`POST /config/reload` 从磁盘活跃路径重新读取、校验、评测并刷新进程缓存；校验失败时继续使用上一份有效配置，并返回 `validation.errors`。所有保存、发布、回滚、导入、导出和重载尝试都必须写入 `AdminAuditLog`，失败操作也要记录 `status=failed` 与错误摘要。

### 3.3 课程 AI 绑定

课程绑定声明某门课程使用哪些 AI 能力。

```http
GET /api/v1/admin/courses/{course_id}/model-config
PUT /api/v1/admin/courses/{course_id}/model-config
```

设计字段：

```ts
interface CourseAiBinding {
  course_id: string
  chat_provider?: string | null
  cloud_rag_provider?: string | null
  cloud_rag_provider_id?: string | null
  remote_knowledge_base_id?: string | null
  default_answer_mode: 'default_chat' | 'course_rag_qa'
  allow_rag_fallback_to_chat: boolean
  require_citation_for_course_answer: boolean
  default_use_course_evidence_for_resource: boolean
  ai_binding_enabled: boolean
  daily_token_limit?: number | null
  daily_cost_limit?: number | null
}
```

### 3.4 资源审核

资源审核用于管理用户提交到资源大厅或社区的内容。

```http
GET  /api/v1/admin/resources/review/stats
GET  /api/v1/admin/resources/review
GET  /api/v1/admin/resources/review/logs
GET  /api/v1/admin/resources/review/{resource_id}
GET  /api/v1/admin/resources/review/{resource_id}/logs
POST /api/v1/admin/resources/review/{resource_id}
```

查询参数：

| 接口 | 参数 | 说明 |
|---|---|---|
| `GET /review/stats` | `course_id` | 可选，按课程统计审核状态。 |
| `GET /review` | `course_id`、`status` | 可选，按课程和审核状态返回队列。 |
| `GET /review/logs` | `course_id`、`resource_id`、`limit` | 可选，返回课程或资源维度审核日志。 |
| `GET /review/{resource_id}/logs` | `limit` | 返回单个资源审核日志。 |

审核动作：

```ts
type ResourceReviewAction =
  | 'approve'
  | 'feature'
  | 'request_changes'
  | 'reject'
  | 'hide'
  | 'archive'
```

审核记录必须包含：

* 审核人；
* 审核动作；
* 审核意见；
* 质量分或质量等级；
* 引用状态；
* 安全审查状态；
* 操作时间。

审核动作行为：

| 动作 | 结果 |
|---|---|
| `approve` | 审核状态更新为 `approved`，资源进入可复用资源池。 |
| `feature` | 审核状态和资源状态更新为 `featured`，资源大厅精选区可展示。 |
| `request_changes` | 审核状态更新为 `changes_requested`，要求用户修改，必须有审核意见。 |
| `reject` | 审核状态更新为 `rejected`，不进入公开资源流，必须有审核意见。 |
| `hide` | 审核状态更新为 `hidden`，从公开资源流移除。 |
| `archive` | 审核状态更新为 `archived`，保留审计记录但不参与分发。 |

前端完成审核动作后必须重新拉取审核统计、队列、详情、日志和资源大厅聚合接口，保证“审核页结果”和“资源大厅卡片 / 详情”一致。

### 3.5 公告发布

管理员公告接口用于 `/admin/announcements`。

```http
GET    /api/v1/admin/announcements/stats
GET    /api/v1/admin/announcements
POST   /api/v1/admin/announcements
GET    /api/v1/admin/announcements/{announcement_id}
PUT    /api/v1/admin/announcements/{announcement_id}
POST   /api/v1/admin/announcements/{announcement_id}/publish
POST   /api/v1/admin/announcements/{announcement_id}/archive
DELETE /api/v1/admin/announcements/{announcement_id}
```

管理字段包括：

* 标题、摘要、Markdown 正文；
* 分类、优先级、展示类型；
* 受众角色：`all`、`student`、`admin`；
* 状态：`draft`、`published`、`archived`、`deleted`；
* 是否置顶、是否可关闭、是否需要确认；
* 自动关闭秒数；
* 行动按钮文案与跳转地址；
* 生效时间与过期时间。

发布约束：

* 只有管理员可创建、编辑、发布、归档或删除公告。
* 删除为软删除，用户阅读和关闭记录保留。
* 用户侧只展示 `published` 且当前时间处于生效窗口内的公告。

### 3.6 界面设置

界面设置接口用于 `/admin/interface-settings`，当前覆盖登录页背景配置。

```http
GET  /api/v1/admin/settings/login-background
PUT  /api/v1/admin/settings/login-background
GET  /api/v1/admin/settings/login-background/media
POST /api/v1/admin/settings/login-background/media
```

配置字段包括：

* `enabled`、`media_type`、`media_url`、`fit`；
* `position_x`、`position_y`、`scale`；
* `brightness`、`contrast`、`saturate`、`blur`；
* `overlay_opacity`、`fallback_color`；
* `updated_at`、`updated_by`。

安全约束：

* 媒体地址只允许站内路径或 `http(s)` 地址。
* 回退底色必须为 `#RRGGBB`。
* 上传媒体应限制文件类型和大小。
* 公开读取接口为 `GET /api/v1/settings/login-background`，不得返回管理员审计细节之外的敏感信息。

### 3.7 运维监控与 Webhook

```http
GET  /api/v1/admin/model-providers/logs
GET  /api/v1/admin/model-providers/traces/{trace_id}
GET  /api/v1/admin/model-providers/usage-stats
POST /api/v1/webhooks/chatdoc/status
```

运维监控至少应能观察：

* Chat 调用成功率；
* 资源生成成功率；
* Cloud RAG 检索命中率；
* 模型调用 P50 / P95 延迟；
* Token 输入输出；
* 预估成本；
* 供应商健康状态；
* 失败错误码和 traceId。

---


### 3.8 助教端（TA Portal）

助教端 API 统一挂载在 `/api/v1/ta` 前缀下，要求登录用户角色为 `ta`。

| 分组 | 前缀 | 能力 |
|---|---|---|
| 工作台 | `GET /ta/dashboard` | 班级、作业、测验、预警与待办聚合统计。 |
| 班级管理 | `/ta/classes` | 班级增删改、邀请码生成/重置、学生增删、名单读取、成绩 CSV 导出。 |
| 作业管理 | `/ta/assignments` | 创建、编辑、发布、关闭课后作业，查看提交列表；支持**多题作业**（从题库选题 `question_ids` / 手动出题 `questions`，题目快照进 `ta_assignment_questions`）与单题旧路径（主观题简答/代码、客观题单选/判断）。 |
| 批改中心 | `/ta/grading` | 批改列表（默认返回全部状态，可按状态/班级过滤）、手动评分、AI 批改（单条/批量/图片/流式）、批改统计与导出；多题作业客观题自动判分、主观题 AI 综合批改，详情与提交列表返回逐题作答与题目快照（含标准答案）。 |
| 测验管理 | `/ta/quizzes` | 创建、编辑、发布、关闭、删除（单个/批量）、查看统计与作答明细；创建时支持从本地题库选题（`question_ids`）或手动输入题目（`questions`），两者可混合。 |
| 本地题库 | `GET /ta/question-bank` | 本地测试题库列表（TA 出题视角含标准答案），支持按课程/题型/关键词过滤；题型为单选/多选/判断/填空四类客观题。 |
| 备课助手 | `/ta/lesson-plans` | AI 生成教案（同步/流式，结构化 JSON 输出）、编辑、发布、删除（单个/批量）。 |
| 学情诊断 | `/ta/diagnosis` | 班级对比、学生趋势/雷达、热力图、进度、薄弱点与教学建议。 |
| 预警管理 | `/ta/alerts` | 预警列表、干预、解决、干预动作与 AI 生成预警。 |
| 资源审核 | `/ta/resources` | 待审资源列表、通过、驳回。 |
| 公告管理 | `/ta/announcements` | 创建、编辑、删除、置顶、撤回；发布时可按班级定向（多选）。 |
| AI 教学助手 | `POST /ta/agent/messages`、`POST /ta/agent/confirm` | 教师端对话式 Agent（有身份、能聊天、能布置任务）：通过 function calling 调用工具，只读查询（班级/学生/作业/题库/测验/课程/知识库）直接执行，写操作（布置作业/发布作业/创建测验/发布公告）返回待确认，教师经 confirm 端点确认后执行。仅 `ta`/`admin` 可访问。 |

关键行为：

* 助教创建作业/测验后默认草稿状态，发布后才对学生可见；关闭后学生不可再提交。
* 智能备课采用**结构化教案契约**：DeepSeek `json_object` 模式输出 `{objectives, key_points, difficulties, process, homework, board}`，后端做字段级防御解析（`objectives` 为必填锚点），解析成功时结构化内容存 `content`（JSONB）、同时渲染 Markdown 存 `outline`（编辑/兼容展示），避免长 Markdown 教案被 `max_tokens` 截断；解析失败降级为占位骨架（`source=fallback`）。AI 生成成功后前端弹出**教案编辑弹窗**，教师可增删改教学重点/目标/难点/过程/作业/板书，保存时整体提交 `content`（`PUT /ta/lesson-plans/{id}`）并同步重渲染 outline；直接编辑大纲文本时结构化内容失效，以编辑文本为准。
* 测验支持删除：仅草稿可删（`DELETE /ta/quizzes/{quiz_id}` 单个、`DELETE /ta/quizzes` 批量，批量返回删除数与跳过的 id），删除时级联清理题目与作答记录；已发布/已关闭的测验禁止删除，避免破坏学生作答数据。
* 布置测验/作业时支持从本地测试题库（`ta_question_bank`，种子含深度学习课程单选 10 题、多选 5 题、判断 6 题、填空 5 题，共 26 题）按四类题型筛选勾选题目，后端把选中题目快照复制进 `ta_quiz_questions` / `ta_assignment_questions`，保证学生作答与判分链路不变；题库本身不直接暴露给学生端。
* 手动评分与 AI 批改均写入 `ta_grading_records`；AI 批改失败时返回明确错误，不伪造分数。支持**批量 AI 批改**（`POST /ta/grading/ai-grade/batch`，最多 100 条，单条失败不影响其余，返回成功/失败统计）。
* 课后作业支持两种形态：
  * **多题作业**（`question_type=multi`）：从题库选题或手动出题组成多题快照，满分按题目分值自动求和；题型为四类客观题（单选 `single_choice`、多选 `multiple_choice`、判断 `true_false`、填空 `blank`）与主观题（简答 `short_answer`、代码 `code`）。学生逐题作答（`POST /ta-student/assignments/{id}/submit` 携带 `answers`），客观题提交后自动判分（多选按选项集合比较、填空忽略大小写），含主观题时客观分记入批改记录 `objective_score`，主观题由 AI 综合批改后汇总总分。
  * **单题旧路径**：主观题（`short_answer`/`code`，学生提交文本作答）与客观题（`single_choice`/`true_false`，学生按选项作答）；客观题必须提供选项与标准答案（`options`/`correct_answer`），学生提交后批改记录携带标准答案（`reference_answer`），AI 批改时按标准答案严格核分。
  * 学生端题目详情（`GET /ta-student/assignments/{id}/questions`）与测验一致，不返回标准答案。
* 干预预警会向学生生成站内通知，学生可在 `/notifications` 查看并标记已读。
* 班级成绩导出为 CSV（UTF-8 BOM），可直接用 Excel 打开。
* 创建班级时服务端生成 8 位唯一邀请码（字符集剔除易混淆字符）；`POST /ta/classes/{class_id}/regenerate-code` 重置后旧码立即失效。
* 学情诊断聚合学习事件与概念掌握度，计算班级平均分、薄弱知识点与趋势。
* 发布公告时可指定目标班级（支持多选，`class_ids`），按班级定向通知该班学生；未指定班级则面向全体学生，公告列表仅展示当前助教发布的公告并附带目标班级名。

## 4. 统一错误、权限与日志

### 4.1 权限规则

| 场景 | 权限要求 |
|---|---|
| 访问课程内对话、资料、资源 | 用户必须拥有课程访问权限。 |
| 无课程普通 Chat | 登录用户即可使用。 |
| 通用资源生成 | 登录用户即可使用。 |
| WebSocket AI 对话与资源进度 | 登录用户通过连接后的 `auth` 帧鉴权；不得依赖 URL 查询参数传递长期 token。 |
| 通用资源归档到课程 | 用户必须拥有目标课程访问权限。 |
| 查看用户公告 | 登录用户只能查看面向自己角色且已发布生效的公告。 |
| 读取登录背景配置 | 未登录也可读取公开配置。 |
| 管理端知识库、网关、审核、运维 | 必须具备管理员权限。 |
| 管理公告发布和界面设置 | 必须具备管理员权限。 |
| 回收站彻底删除 | 必须管理员二次确认，并记录审计日志。 |

### 4.2 错误响应

统一错误结构建议：

```ts
interface ApiError {
  code: string
  message: string
  detail?: Record<string, unknown>
  trace_id?: string
  retry_after_seconds?: number
}
```

常见错误码：

| 错误码 | 场景 | 前端处理 |
|---|---|---|
| `course_required` | 课程资料问答缺少课程 | 提示选择课程。 |
| `course_access_denied` | 无课程访问权限 | 提示无权限并阻断请求。 |
| `chat_provider_missing` | ChatProvider 未配置 | 普通 Chat 和资源生成置灰。 |
| `cloud_rag_provider_missing` | CloudRagProvider 未配置 | 课程资料问答置灰。 |
| `knowledge_not_ready` | 文档未完成向量化 | 提示等待处理完成或切换普通 Chat。 |
| `citation_insufficient` | 引用不足 | 展示引用不足，允许重新检索或普通生成。 |
| `resource_task_quota_exceeded` | 资源生成限流或配额不足 | 显示重试时间。 |
| `resource_task_failed` | 资源生成失败 | ResourceTaskCard 显示失败原因和重试入口。 |
| `safety_blocked` | 安全审查不通过 | 不保存正文，显示拦截原因。 |

### 4.3 限流与配额

* 普通 Chat 按用户和学习范围限流。
* 资源生成按用户和课程 / 通用范围限流。
* 管理端批量向量化、批量萃取应限制单次文档数量。
* 触发限流时返回 `429` 和 `Retry-After`。

### 4.4 日志与 trace

所有关键调用需要写入 trace：

| 调用 | 日志内容 |
|---|---|
| 普通 Chat | 用户、课程、供应商、模型、Token、延迟、状态、traceId。 |
| 意图路由 | 用户、课程、会话、输入摘要、意图、置信度、来源、候选意图、澄清状态、traceId。 |
| 路由反馈 | 用户、输入摘要、预测意图、期望意图、是否正确、备注、traceId。 |
| 课程资料问答 | 课程、知识库、检索耗时、命中片段、引用数量、状态、traceId。 |
| 资源生成 | 任务 ID、智能体阶段、引用覆盖、质量核验、安全审查、状态、traceId。 |
| 管理端操作 | 操作人、动作、目标类型、目标 ID、操作详情、时间。 |
| Webhook | 来源、目标文档、旧状态、新状态、处理结果、错误信息。 |

---

## 5. 核心数据模型

### 5.1 枚举类型

```ts
type LearningScope = 'general' | 'course'

type ResourceType =
  | 'lecture'
  | 'course_doc'
  | 'mindmap'
  | 'quiz'
  | 'remedial_card'
  | 'code_lab'
  | 'reading_pack'
  | 'ppt_outline'
  | 'video_script'
  | 'project_material'

type ResourceStatus =
  | 'private'
  | 'draft'
  | 'saved'
  | 'pending_review'
  | 'changes_requested'
  | 'approved'
  | 'rejected'
  | 'featured'
  | 'hidden'
  | 'archived'
```

### 5.2 ResourceGenerationTask

```ts
interface ResourceGenerationTask {
  id: string
  task_id: string
  requested_by_user_id: string
  scope: 'course' | 'general'
  course_id?: string | null
  concept_id?: string | null
  path_node_id?: string | null
  resource_type: ResourceType
  difficulty: 'basic' | 'medium' | 'advanced'
  goal: string
  requirements?: string | null
  status: ResourceTaskStatus
  progress: number
  steps_json: ResourceGenerationStep[]
  orchestration_json: Record<string, unknown>
  draft_content?: string | null
  outline_json: OutlineSection[]
  citations?: Citation[]
  result_resource_id?: string | null
  error_code?: string | null
  error_message?: string | null
  attempt_count: number
  max_attempts: number
  trace_id?: string | null
  created_at: string
  updated_at: string
}
```

### 5.3 Resource

```ts
interface Resource {
  id: string
  course_id?: string | null
  concept_id?: string | null
  path_node_id?: string | null
  code: string
  scope: 'course' | 'general'
  owner_scope?: 'mine' | 'community' | null
  course_bound: boolean
  course_evidence_required: boolean
  title: string
  resource_type: ResourceType
  difficulty: string
  status: ResourceStatus
  summary: string
  content?: string | null
  content_uri?: string | null
  generation_basis_json: {
    prompt?: string
    personalization?: Record<string, unknown>
    evidence_policy?: Record<string, unknown>
    trace_id?: string
  }
  citations_json: Citation[]
  quality_check_result: QualityCheckResult
  safety_status: 'passed' | 'blocked' | 'manual_review'
  quality_score: number
  latest_version?: number | null
  view_count: number
  copied_count: number
  community_id?: string | null
  review_status?: ResourceStatus | null
  submitted_at?: string | null
  reviewed_at?: string | null
  review_comment?: string | null
  submitted_by?: string | null
  reviewed_by?: string | null
  recommendation_score?: number | null
  match_reason?: string | null
  recommendation_evidence: Array<{
    key: string
    label: string
    summary: string
    source?: string | null
    score?: number | null
  }>
  badges: string[]
  is_featured: boolean
  is_recommended: boolean
  thumbnail_url?: string | null
  created_by_user_id?: string | null
  created_at: string
  updated_at: string
}
```

资源大厅和资源审核可以复用同一 `Resource` 响应结构，但必须区分：

* `status` 表示资源自身生命周期；
* `review_status` 表示社区审核记录状态；
* `owner_scope` 表示当前用户视角下的归属范围；
* `is_featured`、`is_recommended`、`recommendation_score`、`match_reason` 和 `recommendation_evidence` 只用于大厅分发和推荐解释；
* `recommendation_evidence` 按课程匹配、画像匹配、薄弱点、掌握度短板、最近学习事件、课程引用和质量复用等维度解释推荐原因；
* `view_count`、`copied_count`、`citations_json`、`quality_score` 在卡片和详情中必须保持一致。

### 5.4 ResourceVersion

```ts
interface ResourceVersion {
  id: string
  resource_id: string
  version: number
  content: string
  meta_json: {
    title?: string
    summary?: string
    editor?: string
    change_reason?: string
    restored_from_version?: number
  }
  created_at: string
  updated_at: string
}
```

### 5.5 Citation

```ts
interface Citation {
  source_id: string
  source_title: string
  page_no?: number | null
  iflytek_file_id?: string | null
  chunk_index?: number | null
  local_chunk_id?: string | null
  provenance_source?: string | null
  chunk_id?: string | null
  kind: 'chunk' | 'page' | 'element'
  page_asset_id?: string | null
  element_id?: string | null
  asset_type?: 'TEXT' | 'IMAGE' | 'TABLE' | 'FORMULA' | null
  heading_path_text?: string | null
  heading_number?: string | null
  bbox?: number[] | null
  bbox_norm?: number[] | null
  evidence_uri?: string | null
  section_path?: string | null
  retrieval_mode?: string | null
  fusion_score?: number | null
  rerank_score?: number | null
  similarity: number
  snippet: string
  content?: string | null
}
```

### 5.6 Document 与 DocumentChunk

```ts
interface Document {
  id: string
  course_id: string
  uploaded_by_user_id?: string | null
  title: string
  filename: string
  mime_type?: string | null
  source_type: 'course_material' | 'teacher_upload' | 'admin_upload'
  parse_status: string
  vector_status: string
  text_vector_status: string
  visual_vector_status: string
  publish_readiness: 'blocked' | 'ready'
  file_uri?: string | null
  content_hash?: string | null
  ingestion_version: number
  parser_version?: string | null
  chunker_version?: string | null
  meta_json: Record<string, unknown>
  deleted_at?: string | null
  created_at: string
  updated_at: string
}

interface DocumentChunk {
  id: string
  document_id: string
  course_id: string
  concept_id?: string | null
  page_asset_id?: string | null
  chunk_index: number
  page_no?: number | null
  section_path?: string | null
  asset_type: 'TEXT' | 'IMAGE' | 'TABLE' | 'FORMULA'
  heading_path_text?: string | null
  heading_number?: string | null
  bbox_json?: number[] | null
  bbox_norm_json?: number[] | null
  content: string
  raw_text?: string | null
  lifecycle_status: 'active' | 'deleted'
  embedding_status: string
  embedding_model: string
  embedding_dim: number
  quality_score: number
  quality_reasons_json: string[]
  created_at: string
  updated_at: string
}
```

### 5.7 LearningProfile 与 ProfileEvidence

```ts
interface ProfileEvidence {
  id: string
  user_id: string
  scope: 'global' | 'course' | 'session' | 'cross_course'
  course_id?: string | null
  conversation_id?: string | null
  dimension: string
  label: string
  source_type: 'conversation' | 'assessment' | 'resource_usage' | 'path_progress' | 'user_correction'
  source_id: string
  confidence_delta: number
  summary: string
  created_at: string
}

interface LearningProfileSnapshot {
  id: string
  user_id: string
  scope: 'global' | 'course' | 'session' | 'cross_course'
  course_id?: string | null
  conversation_id?: string | null
  summary: string
  dimensions: Record<string, unknown>
  evidence_ids: string[]
  confidence: number
  updated_at: string
}
```

### 5.8 Announcement 与 UserAnnouncementState

```ts
type AnnouncementStatus = 'draft' | 'published' | 'archived' | 'deleted'
type AnnouncementPriority = 'info' | 'success' | 'warning' | 'critical' | 'maintenance'
type AnnouncementDisplayType = 'top_bar' | 'modal' | 'page_card' | 'toast' | 'list_only'
type AnnouncementAudience = 'all' | 'student' | 'admin'

interface Announcement {
  id: string
  title: string
  summary: string
  body: string
  category: string
  priority: AnnouncementPriority
  display_type: AnnouncementDisplayType
  audience_role: AnnouncementAudience
  status: AnnouncementStatus
  pinned: boolean
  dismissible: boolean
  require_confirmation: boolean
  auto_dismiss_seconds?: number | null
  action_label?: string | null
  action_url?: string | null
  effective_at?: string | null
  expires_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

interface UserAnnouncementState {
  announcement_id: string
  user_id: string
  is_read: boolean
  is_dismissed: boolean
  display_type?: AnnouncementDisplayType | null
  confirmed_at?: string | null
  dismissed_at?: string | null
}
```

### 5.9 LoginBackgroundSettings

```ts
interface LoginBackgroundSettings {
  enabled: boolean
  media_type: 'image' | 'video'
  media_url: string
  fit: 'cover' | 'contain'
  position_x: number
  position_y: number
  scale: number
  brightness: number
  contrast: number
  saturate: number
  blur: number
  overlay_opacity: number
  fallback_color: string
  updated_at?: string | null
  updated_by?: string | null
}

interface LoginBackgroundMediaAsset {
  filename: string
  media_url: string
  media_type: 'image' | 'video'
  source: 'built_in' | 'server_upload'
  size?: number | null
  updated_at?: string | null
}
```

### 5.10 ModelProvider 与 ModelCallLog

```ts
interface ModelProvider {
  id: string
  provider: string
  display_name: string
  provider_type: 'chat' | 'embedding' | 'vision' | 'doc_qa' | 'resource_agent' | 'both'
  base_url?: string | null
  protocol: 'openai_compatible' | 'iflytek_chatdoc' | 'custom'
  chat_model?: string | null
  embedding_model?: string | null
  embedding_dimension?: number | null
  vision_model?: string | null
  supports_stream: boolean
  supports_tool_call: boolean
  supports_json_mode: boolean
  health_status: 'healthy' | 'standby' | 'degraded' | 'failed'
  priority: number
  is_active: boolean
  is_default: boolean
  last_checked_at?: string | null
  daily_limit?: number | null
  cost_config_json: Record<string, unknown>
  meta_json: Record<string, unknown>
}

interface ModelCallLog {
  id: string
  course_id?: string | null
  user_id?: string | null
  provider_id?: string | null
  agent_name?: string | null
  capability: ModelProviderCapability
  model_name?: string | null
  token_input: number
  token_output: number
  latency_ms: number
  status: 'success' | 'failed' | 'fallback' | 'degraded'
  error_message?: string | null
  trace_id?: string | null
  meta_json: Record<string, unknown>
  created_at: string
}
```

### 5.11 AdminAuditLog

```ts
interface AdminAuditLog {
  id: string
  actor_user_id?: string | null
  action: string
  target_type: 'course' | 'document' | 'chunk' | 'resource' | 'provider' | 'knowledge'
  target_id: string
  detail_json: Record<string, unknown>
  created_at: string
}
```

---

## 6. 数据关系与生命周期

### 6.1 资源生成关系

```text
User
  ↓
ResourceGenerationTask
  ├─ ProfileSnapshot / ProfileEvidence
  ├─ Citation[]
  ├─ ResourceGenerationStep[]
  └─ Resource
       ├─ ResourceVersion[]
       ├─ citations_json
       ├─ generation_basis_json
       └─ CommunityResource / ResourceReview
```

要求：

* `ResourceGenerationTask` 记录生成过程，`Resource` 记录可复用成果。
* `ResourceVersion` 记录正文版本，不替代任务状态。
* `citations_json` 记录引用来源，不应污染资源正文。
* `generation_basis_json` 可以记录画像使用摘要，但不得暴露完整敏感画像。

### 6.2 课程资料关系

```text
Course
  ↓
Document
  ├─ DocumentPage[]
  ├─ DocumentChunk[]
  ├─ VectorizationTask[]
  └─ RetrievalVerificationRun[]
```

要求：

* 只有 `Document` 和 `DocumentChunk` 处于可检索状态时，课程资料问答和基于课件生成才可使用。
* 删除文档时应同时处理本地记录、云端文件引用和检索索引。
* 回收站文档不得参与检索。

### 6.3 AI 调用关系

```text
AiMessageRequest
  ↓
AiOrchestratorService
  ├─ HybridIntentRouter
  ├─ ProfileContextResolver
  ├─ CourseAiBindingService
  ├─ ChatProvider
  ├─ CloudRagProvider
  └─ TraceService
       ↓
ModelCallLog
```

要求：

* 意图路由、普通 Chat、学习进度查询、课程资料问答、资源生成都应产生 trace。
* trace 需要能在管理端按供应商、能力、课程、用户和时间筛选。
* `intent_route` 日志必须记录意图、置信度、来源、候选项和命中原因。
* `intent_feedback` 日志必须记录预测意图、期望意图、是否正确和备注。
* 失败调用同样记录日志，不能只在前端展示错误。

---

## 7. 功能验收标准

### 7.1 用户侧验收

1. `/dashboard` 默认输入调用 ChatProvider，不默认调用文档问答 API。
2. 用户未选择课程时，普通 Chat 和通用资源生成可用。
3. 用户未选择课程时，课程资料问答不可用，并提示需要选择课程。
4. 用户显式选择“课程资料问答”后，请求使用 `mode = 'course_rag_qa'`。
5. 课程资料问答返回答案时展示引用来源；未命中时展示引用不足或不可用原因。
6. 课程资料问答不创建 ResourceTaskCard，不打开 ArtifactCanvas。
7. 用户触发资源生成后，系统创建 ResourceTaskCard，并展示任务状态、进度、当前智能体阶段和失败原因。
8. 点击 ResourceTaskCard 可打开 ArtifactCanvas。
9. ArtifactCanvas 支持预览、编辑、保存、版本恢复、重新生成和提交审核；其中阶段测评题资源必须展示为可填写、可选择、可暂存、可提交评分的在线测评工作台，而不是只读 Markdown 试卷。
10. ArtifactCanvas 支持前端本地导出 Markdown、DOCX、PPTX 和浏览器打印 / 另存 PDF，其中 DOCX 使用 `docx`、PPTX 使用 `pptxgenjs` 按需生成，不要求新增后端导出 API。
11. ArtifactCanvas 的 Inspector 能展示规划、取证、生成、核验、安全、保存的多智能体工作流概览，并保留原始 Trace 时间线。
12. 有课程资源生成默认绑定 `course_id / concept_id / path_node_id`。
13. 无课程资源生成默认 `scope = 'general'`，保存后可归档到课程。
14. 课程内资源生成默认先检索课程依据；未命中可靠依据时必须继续由 ChatProvider 直接生成，并标注无可核验引用。
15. 基于课程资料生成时，ArtifactCanvas 必须展示引用或引用不足提示。
16. 资源生成失败时，卡片必须有明确错误状态和重试入口。
17. 用户纠正画像后，后续回答和资源生成优先使用纠偏结果。
18. 用户询问“我学到哪了”“学习进度怎么样”“下一步该学什么”时，系统返回 `learning_progress`，并基于真实学情数据回答。
19. 用户在学习进度回答后追问“那下一步呢”时，前端应通过 `clientContext.lastIntentRoute` 带上上一轮 route，后端继续识别为学习进度追问。
20. 用户在学习进度回答后输入“我要学”时，后端不得继承为学习进度查询，应识别为开始学习或学习计划。
21. 用户问“课件里怎么定义 X”时走课程资料问答；用户问“解释一下 X”时默认走普通 Chat。
22. 用户问“根据我的薄弱点出题”时走资源生成，不应误判为只查看学习进度。
23. `semantic-router` 可用并返回候选时，路由候选来源不得只是 `small_model`。
24. 用户登录后顶部导航能显示公告未读数，并可进入 `/announcements` 查看详情、标记已读和关闭展示。
25. 用户可在个人设置中修改显示名称、导出设置摘要、清理本地草稿并安全退出登录。
26. 登录页和注册页能在未登录状态读取公开登录背景配置。
27. 学习日历能从学习路径、资源和公告聚合日期事项，并跳转到对应页面继续操作。
28. 练习评估支持学生在线作答，答题中不开放问 AI，提交后能返回得分、错题归因、掌握度影响或异步排队状态，并在评分后开放 AI 解析入口。
29. 资源画布中的阶段测评题能解析题目、标准答案和评分要点；学生可直接在画布内选择或填写答案，提交后通过 `POST /api/v1/assessments` 评分并更新画像。若缺少标准答案、评分要点或课程知识点绑定，前端必须明确阻止可靠自动评分并说明原因。
30. 学习路径的原始教材 PDF 预览支持章节目录、全文搜索、搜索历史、最近阅读页恢复、页码跳转、书签和页面笔记，页面笔记可删除当前页并导出 Markdown，搜索命中能跳转并在当前页高亮。

### 7.2 管理侧验收

1. 知识大本营能上传 PDF / TXT / MD，并展示解析、切分、向量化和可问答状态。
2. 知识大本营能查看分段、原文页码、引用片段和检索测试结果。
3. 知识大本营 PDF 原文工作台支持目录、全文搜索、搜索历史、最近阅读页恢复、当前页切片、书签和笔记，笔记可删除当前页并导出 Markdown，目录或搜索结果点击后能定位到对应页；扫描型 PDF 或文本层不可用时，搜索仍可通过本地切片命中并定位。
4. 文档未完成向量化时，用户侧课程资料问答和基于课件生成不可用。
5. 回收站能展示已删除文档，支持还原和彻底删除。
6. 网关中心能创建、编辑、删除、测试模型供应商。
7. 网关中心必须区分 ChatProvider、Embedding、Vision、Doc QA 和 Resource Agent 能力。
8. ChatProvider 未配置或不健康时，普通 Chat 和资源生成不可用并有提示。
9. CloudRagProvider 未配置或不健康时，课程资料问答不可用，但普通 Chat 不受影响。
10. 课程 AI 绑定能配置 ChatProvider、CloudRagProvider、远端知识库 ID 和引用策略。
11. 资源审核能通过真实接口查看资源正文、引用、AI 初检、质量分、版本、生成 trace 和审核日志。
12. 审核通过后资源进入可复用资源池；精选后进入资源大厅精选区；驳回或要求修改时记录审核意见。
13. 审核动作完成后，审核统计、队列、详情、日志和资源大厅聚合数据必须同步刷新。
14. 运维监控能查看调用日志、trace 详情、用量统计、成本估算和失败趋势。
15. 网关中心调用日志能筛选 `intent_route` 和 `intent_feedback`。
16. 意图路由日志能展示置信度、来源、候选意图、澄清状态和命中原因。
17. 网关中心能可视化编辑 Intent Registry，并支持 YAML 原文编辑、校验、评测、发布、回滚、导入导出和从文件重新加载。
17. 直接编辑 `INTENT_ROUTER_REGISTRY_PATH` 指向的 YAML 文件后，管理员能在后台触发重新加载；校验失败时继续使用上一份有效配置。
18. 公告发布能创建、编辑、发布、归档和删除公告，用户侧按受众、时间窗口和展示类型生效。
19. 界面设置能上传或选择登录背景媒体，保存后 `/login` 和 `/register` 通过公开配置生效。

### 7.3 数据与安全验收

1. 所有课程内 API 必须校验课程访问权限。
2. 管理侧 API 必须校验管理员权限。
3. API 密钥、令牌、密文不得明文返回给前端或写入文档。
4. 资源生成创建接口支持 `X-Idempotency-Key`，重复提交不会创建重复任务。
5. 限流触发时返回 `429` 和 `Retry-After`。
6. 所有资源生成任务必须记录状态、步骤、进度、错误信息和 traceId。
7. 每个画像维度必须有来源、置信度和更新时间。
8. 用户纠偏证据优先级高于系统推断证据。
9. 低置信度业务意图不能直接读取个人学习进度、切换课程资料问答或创建资源生成任务，必须先澄清或回退普通 Chat。
10. 删除或回收的课程资料不得参与检索。
11. 所有管理端关键操作必须写入审计日志。
12. 用户公告阅读和关闭状态必须按用户隔离，不能影响其他用户。
13. 登录背景公开配置不得暴露服务器本地绝对路径、上传目录内部细节或管理员敏感信息。
14. Intent Router 配置文件不得保存密钥；后台编辑和直接文件编辑必须共享同一套 schema 校验、评测和审计流程。
15. 结构化模型输出必须记录 schema 名称、校验结果、修复次数和标准化错误码；工具调用必须记录工具名、权限上下文、参数摘要、幂等键和执行状态。

---


### 7.4 助教端验收

* 助教登录后可在 `/ta` 看到班级统计、趋势图、待办与预警。
* 作业闭环：创建 → 发布 → 学生提交 → 手动/AI 批改 → 学生查看成绩。
* 测验闭环：创建（客观题）→ 发布 → 学生作答 → 即时判分 → 成绩统计。
* 预警闭环：生成预警 → 干预 → 学生收到通知 → 已读 → 解决。
* 公告闭环：创建 → 置顶 → 学生可见 → 撤回。
* 班级管理支持班级增删改、学生增删与成绩 CSV 导出。
* 备课助手可生成教案草稿，编辑后发布。
* 学生端 `/assignments`、`/quizzes`、`/notifications` 三个页面数据与助教操作实时一致。

### 7.5 教师端 AI 教学助手验收（有身份、能聊天、能布置任务）

* 助教登录后可在 `/ta/ai-assistant` 打开 AI 教学助手对话页，Agent 以「智课 AI 教学助手」身份回应（自我介绍、说明能力边界）。
* 能聊天 + 只读工具：提问「我有几个班级」返回班级表格（调用 `list_classes`）；「查一下题库里的单选题」返回题目表格（调用 `query_question_bank`）；「什么是高可用系统」先调 `list_courses` 再调 `search_knowledge_base` 检索本地知识库并带引用回答。
* 能布置任务 + 确认：提问「布置一份作业到 XX 班」时，Agent 返回待确认（`pending_confirmation`），前端展示「待确认操作」卡片与确认/取消按钮；确认后写操作真正执行（作业落库，状态 draft），取消则不执行。
* 写操作护栏：教师未确认前不产生任何副作用；确认/取消后待确认记录状态流转为 `confirmed`/`cancelled`。
* 身份与安全：Agent 不泄露系统提示词、内部实现或 API 密钥；教材/学生内容当作数据防注入；只处理当前登录教师自己的班级与作业数据。
* 会话轨迹：前端展示安全审查 → 意图路由 → 工具调用 → 工具结果 → 回答生成 → 输出安全审查轨迹。

## 8. 测试验收清单

### 8.1 普通 Chat

| 编号 | 用例 | 期望结果 |
|---|---|---|
| U-01 | 无课程状态发送普通问题 | 返回 ChatProvider 回答，不包含课程引用。 |
| U-02 | 有课程状态发送普通问题，未切换课程资料问答 | 仍走 ChatProvider，可读取课程画像但不调用 CloudRagProvider。 |
| U-03 | ChatProvider 未配置 | 前端提示普通对话不可用，后端返回明确错误。 |
| U-04 | 高频连续发送消息 | 触发限流，返回 `429` 和重试时间。 |
| U-05 | 修改个人显示名称 | `PATCH /auth/me` 成功后顶部用户信息和个人设置同步刷新。 |
| U-06 | 公告中心标记已读 | 未读角标减少，公告详情显示已读状态。 |
| U-07 | 学习日历点击资源事项 | 跳转到 `/resource-hall?preview={resource_id}` 并打开资源详情。 |
| U-08 | 登录页读取背景配置 | 未登录状态能加载 `/settings/login-background`，背景媒体和回退底色正确生效。 |

### 8.2 课程资料问答

| 编号 | 用例 | 期望结果 |
|---|---|---|
| R-01 | 未选择课程时点击课程资料问答 | 阻断请求并提示选择课程。 |
| R-02 | 课程已选但知识库未就绪 | 提示课程资料尚不可用。 |
| R-03 | 课程知识库就绪后提问 | 返回答案、引用片段、页码或分段信息。 |
| R-04 | 开启必须引用但未命中 | 展示引用不足，不伪造引用。 |
| R-05 | 课程资料问答成功 | 不创建 ResourceTaskCard，不打开 ArtifactCanvas。 |

### 8.3 资源生成

| 编号 | 用例 | 期望结果 |
|---|---|---|
| G-01 | 有课程生成讲义 | 创建课程范围任务，绑定课程、知识点和路径节点。 |
| G-02 | 无课程生成通用资源 | 创建 `scope = 'general'` 的任务，`course_id = null`。 |
| G-03 | 基于课件生成思维导图 | 先检索课程资料，再生成 Markmap 兼容 Markdown，并展示引用。 |
| G-04 | 重复点击生成按钮且幂等键相同 | 只创建一个任务。 |
| G-05 | 任务失败后点击重试 | 任务重新进入队列，保留历史错误和新 trace。 |
| G-06 | 安全审查失败 | 不保存资源正文，卡片展示安全拦截。 |
| G-07 | 用户编辑并保存资源 | 生成或更新 ResourceVersion，可恢复历史版本。 |
| G-08 | 通用资源归档到课程 | 校验课程权限，归档后资源变为课程资源。 |
| G-09 | 阶段测评题结构化输出缺少标准答案或评分要点 | 后端校验失败并触发结构化修复；连续失败后返回稳定错误码，前端不展示为可作答题单。 |
| G-10 | 模型请求调用具有副作用的工具 | 后端校验工具白名单、权限、参数 schema、幂等键和限流后才执行，并在 trace 中记录执行状态。 |

### 8.4 管理端

| 编号 | 用例 | 期望结果 |
|---|---|---|
| A-01 | 上传重复文档 | 根据策略阻断或提示强制重新上传。 |
| A-02 | 文档处理失败 | 文档列表显示失败原因，用户侧不可用。 |
| A-03 | 检索测试 | 返回命中片段、相似度、耗时和引用来源。 |
| A-04 | 新增模型供应商并测试 | 健康状态、模型名、延迟和错误信息正确记录。 |
| A-05 | 设置默认 ChatProvider | 后续普通 Chat 使用默认供应商。 |
| A-06 | 审核资源通过 | 资源进入可复用资源池并记录审核日志。 |
| A-07 | 清除或筛选调用日志 | 只影响当前筛选范围，并记录管理员操作。 |
| A-08 | 发布顶部条公告 | 学生端顶部未读角标和公告中心同步出现该公告。 |
| A-09 | 保存登录背景设置 | 登录页和注册页刷新后展示新的背景媒体与视觉参数。 |

### 8.5 回归测试建议

| 范围 | 建议命令 | 说明 |
|---|---|---|
| 后端资源生成 | `pytest backend/tests/test_resource_generation_task.py` | 验证任务创建、重试、状态和引用。 |
| 后端画像 | `pytest backend/tests/test_learning_profile_repository.py backend/tests/test_profile_extractor.py` | 验证画像证据和纠偏。 |
| 后端知识库 | `pytest backend/tests/test_knowledge_upload_policy.py backend/tests/test_native_chunks_routes.py` | 验证上传策略和分段接口。 |
| 本地知识库回归 | `pytest backend/tests/test_local_knowledge_markdown.py backend/tests/test_knowledge_regressions.py` | 验证 Markdown 解析、课程就绪、先修关系、权限过滤和本地检索。 |
| 前端全量测试 | `pnpm test`（在 `frontend` 目录） | 验证 API 契约、组件逻辑和前端治理规则。 |
| 前端构建 | `pnpm build`（在 `frontend` 目录） | 验证 TypeScript 和生产构建。 |
| 全量守卫 | `make guard` | 合并前优先执行后端静态检查和关键 smoke tests。 |

---

## 9. 软件杯演示验收路径

建议演示时按以下顺序验证闭环：

```text
管理员配置 ChatProvider 和 CloudRagProvider
  ↓
上传课程资料并完成向量化
  ↓
用户进入 /dashboard 选择课程
  ↓
普通 Chat 回答一个概念问题
  ↓
显式切换课程资料问答并展示引用
  ↓
基于当前知识点生成个性化资源
  ↓
ResourceTaskCard 展示任务进度
  ↓
ArtifactCanvas 展示正文、引用、画像摘要和版本
  ↓
用户编辑保存并提交资源大厅
  ↓
管理员审核通过
  ↓
资源大厅可检索复用
  ↓
运维监控查看 trace、调用日志、成本和失败率
```

该路径覆盖用户侧、管理侧、AI 编排、课程资料、资源生成、画像、审核和运维监控，是项目验收的最小完整闭环。

## T-B-07 本地知识库验收补充

- `RAG_BACKEND=local_pgvector` 时复用现有知识库上传和检索路由，不删除 ChatDoc 路由或配置。
- 当前已导入 7 条课程主线共 1165 份本地文档、24167 个可检索切片。
- `GET /api/v1/courses/with-knowledge` 必须返回 7 门已就绪课程；学生结果应受选课范围限制，管理员可返回全部。
- `data_system` 课程查询“高可用系统”应返回 `retrieval_mode=local_pgvector`、相关片段、页码和本地切片 ID。
- 本地解析支持 PDF、Markdown、MDX 和纯文本；扫描版 PDF 仍需 OCR。
- 本地向量为 BGE-small-zh-v1.5 的 512 维；模型权重不进入仓库，首次运行前确认 `LOCAL_EMBEDDING_CACHE_DIR`。
- Markdown 标题路径按数据库列宽安全截断，完整路径保留在 JSON 元数据中。
- 前端生产构建、`tsc --noEmit`、Vitest 全量测试和后端 Ruff 检查均需通过后再合并。

### 历史验收要点

- RAG_BACKEND=local_pgvector 时复用现有知识库上传和检索路由，不删除 ChatDoc 路由或配置。
- 上传 PDF 后应完成 PyMuPDF 解析、保留页码的文本分块、512 维本地向量化、PGVector 入库。
- 输入明确问题后，检索响应必须返回 `retrieval_mode=local_pgvector`、相关片段、页码和本地切片 ID。

- 模型权重不进入仓库；首次运行前由操作者确认下载目录，Windows 推荐配置到 D 盘。
