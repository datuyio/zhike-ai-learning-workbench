# AI 编排与能力解耦设计

## 1. 设计目标

AI 编排层负责把用户侧页面动作、显式模式、课程上下文、画像上下文、资源生成意图和管理端模型配置统一调度起来。

核心目标：

1. **普通 Chat / Agent 能力与 Cloud RAG / 课程资料问答能力彻底解耦**。
2. **前端不直接判断调用哪个厂商 API**，只提交业务动作和上下文。
3. **Adapter 只做协议适配，不做业务意图判断**。
4. **支持有课程与无课程两种模式**。
5. **支持资源生成前按需调用课程资料依据**，但资源正文生成仍由 ChatProvider / ResourceAgent 完成。
6. **所有 AI 调用可追踪、可观测、可回放、可审计**。

---

## 2. AI 能力边界

系统中的 AI 能力拆分为两类。

### 2.1 Chat / Agent 能力

Chat / Agent 能力用于所有不依赖厂商云端文档库的学习交互和生成任务。

适用范围：

* 普通学习对话；
* 无课程通用问答；
* 知识点解释；
* 智能辅导；
* 学习路径建议；
* 学情画像分析；
* 高白话讲义生成；
* PyTorch 实操案例生成；
* 阶段测评题生成；
* 错题补救卡生成；
* 拓展阅读包生成；
* 多智能体资源生成工作流；
* 资源内容重写和版本生成。

该能力由 **ChatProvider** 提供。

典型供应商：

* OpenAI；
* 通义千问；
* DeepSeek；
* 智谱；
* 讯飞星火通用对话模型；
* 自定义 OpenAI-compatible 服务。

### 2.2 Cloud RAG / 课程资料问答能力

Cloud RAG / 课程资料问答能力用于处理已经上传到对应厂商服务器的课程文档。

适用范围：

* 课程 PDF / TXT / MD 上传；
* 云端文档解析；
* 文档切分；
* 文档向量化；
* 文档状态同步；
* 基于已上传课程资料的问答；
* 引用来源返回；
* 管理端检索测试；
* 资源生成前的课程资料依据提取。

该能力由 **CloudRagProvider** 提供。

典型供应商：

* 讯飞 ChatDoc；
* 百度千帆知识库；
* 阿里云知识库；
* 火山知识库；
* 自定义 RAG 服务。

关键边界：

```text
Cloud RAG / 文档问答 API 只能回答已经上传到对应厂商服务器并完成解析、切分、向量化的文档内容。
它不能替代 Chat / Agent 能力，也不能承担首页普通对话和资源生成的大脑。
```

### 2.3 教师端 AI 教学助手（TaAgentOrchestratorService）

教师端（TA Portal）提供独立的对话式 Agent 入口 `POST /api/v1/ta/agent/messages`，
由 `backend/app/services/ta/agent.py` 的 `TaAgentOrchestratorService` 编排，定位为
**有身份、能聊天、能布置任务的智能体**（借鉴「yueyang tower」教师端助教设计），
与学习端 `AiOrchestratorService` 互补。

身份提示词采用六模块结构（`backend/app/services/ta/prompts.py`）：
①角色与语境 ②能力边界 ③数据真实性与工具纪律 ④任务执行规则 ⑤输出与表达 ⑥安全红线。

能力通过 **function calling 工具集**（`backend/app/services/ta/tools.py`）暴露：

* 只读工具（直接执行）：`list_classes` 列班级、`list_class_students` 列学生、
  `list_assignments` 列作业、`query_question_bank` 检索题库、`list_quizzes` 列测验、
  `list_courses` 列课程、`search_knowledge_base` 检索本地知识库；
* 写工具（需教师确认）：`create_assignment` 布置作业、`publish_assignment` 发布作业、
  `create_quiz` 创建测验、`create_announcement` 发布公告。

关键边界：

```text
写操作由模型「提出工具名与参数」，后端先落待确认记录（ta_agent_confirmations）并暂停，
教师经 POST /api/v1/ta/agent/confirm 确认后才真正执行——模型不得绕过后端直接产生副作用。
只读查询与知识库检索可直接执行；知识问答证据不足时明确拒答（零幻觉防线）。
```

该能力由 **ChatProvider（function calling）+ 本地 pgvector 知识库** 提供，`RAG_BACKEND=local_pgvector` 时生效。

---

## 3. 总体调用原则

`/dashboard` 是 AI 学习工作台，不是厂商文档问答页面。

```text
普通学习对话
  → ChatProvider

课程资料问答
  → CloudRagProvider

资源生成
  → ResourceAgent + ChatProvider

带课程资料依据的资源生成
  → CloudRagProvider 获取依据
  → ResourceAgent + ChatProvider 生成资源
```

前端统一调用后端业务 API。后端由 `AiOrchestratorService` 根据用户动作、显式模式、课程绑定、画像上下文、知识库状态和资源类型进行调度。

---

## 4. 核心服务分层

```text
前端页面 /dashboard、/ai-room、/learning-path、/resource-hall
  ↓
业务 API 层
  ↓
AiOrchestratorService
  ├─ IntentRouter
  ├─ ProfileContextResolver
  ├─ CourseAiBindingService
  ├─ ChatService
  ├─ CourseRagQaService
  ├─ ResourceAgentService
  ├─ SafetyService
  ├─ VerifyService
  └─ TraceService
      ↓
Provider 层
  ├─ ChatProvider
  └─ CloudRagProvider
      ↓
Adapter 层
  ├─ OpenAIAdapter / DeepSeekAdapter / QwenAdapter / ...
  └─ ChatDocAdapter / QianfanKbAdapter / ...
```

---

## 5. AiOrchestratorService

`AiOrchestratorService` 是用户侧 AI 请求的统一编排入口。

### 5.1 职责

* 接收 `/dashboard` 和 `/ai-room` 的统一 AI 请求；
* 判断任务模式和动作类型；
* 读取当前课程绑定；
* 读取有效画像上下文；
* 检查 ChatProvider 和 CloudRagProvider 可用性；
* 决定调用 ChatProvider、CloudRagProvider 或 ResourceAgent；
* 处理无课程通用场景；
* 处理课程资料未命中或服务不可用时的提示；
* 记录 trace；
* 返回统一消息结构。

### 5.2 输入参数

```ts
interface AiMessageInput {
  userId: string
  conversationId?: string
  courseId?: string | null
  pathNodeId?: string | null
  conceptId?: string | null
  message: string
  mode?: 'default_chat' | 'course_rag_qa'
  actionType?: 'chat' | 'resource_generation'
  resourceType?: ResourceType
  needCourseEvidence?: boolean
  uploadedDocId?: string | null
  clientContext?: Record<string, unknown>
}
```

### 5.3 编排伪代码

```ts
async function handleAiMessage(input: AiMessageInput) {
  const scope = input.courseId ? 'course' : 'general'

  const profileContext = await profileContextResolver.resolve({
    userId: input.userId,
    courseId: input.courseId ?? null,
    conversationId: input.conversationId,
    taskType: input.actionType ?? 'chat',
    message: input.message,
    resourceType: input.resourceType,
    pathNodeId: input.pathNodeId,
    uploadedDocId: input.uploadedDocId
  })

  const binding = input.courseId
    ? await courseAiBindingService.get(input.courseId)
    : await modelGatewayService.getDefaultGeneralBinding()

  if (input.mode === 'course_rag_qa') {
    assertCourseSelected(input.courseId)
    return courseRagQaService.answer({
      userId: input.userId,
      courseId: input.courseId,
      question: input.message,
      binding,
      profileContext
    })
  }

  if (input.actionType === 'resource_generation') {
    return resourceAgentService.createTask({
      userId: input.userId,
      courseId: input.courseId ?? null,
      scope,
      resourceType: input.resourceType,
      prompt: input.message,
      needCourseEvidence: Boolean(input.needCourseEvidence && input.courseId),
      binding,
      profileContext
    })
  }

  return chatService.chat({
    userId: input.userId,
    courseId: input.courseId ?? null,
    scope,
    message: input.message,
    binding,
    profileContext
  })
}
```

---

## 6. IntentRouter

IntentRouter 用于把自然语言请求路由到普通 Chat、开始学习、学习计划、学习进度查询、课程资料问答或资源生成。它不是单纯的关键词分类器，而是面向商业化学习产品的 **学习意图调度中枢**：识别用户真正想完成的学习动作，并把请求交给对应的 Chat / Agent / RAG / 学情服务。

当前实现采用 `HybridIntentRouter`。短期目标是保留该对外入口，升级为可插拔、可评测、可审计的 Intent Routing Platform。路由结果统一由 HTTP `/api/v1/ai/messages` 和 WebSocket `/ws/ai/{conversation_id}` 共用，避免不同入口识别结果不一致。WebSocket 鉴权通过连接后的 `auth` 帧完成，不在 URL 查询参数中传递长期 token。

### 6.1 优先级

```text
显式 mode / actionType / intentType
  > 课程上下文、权限、风险等级等业务规则
  > 高精度业务规则
  > 上一轮 route / clientContext 短追问上下文
  > Intent Registry + 语义路由 Provider
  > 可选 LLM Judge 结构化判别
  > 置信度校准、低置信度澄清与灰度策略
  > 默认 Chat
```

### 6.2 路由输出

```ts
type IntentType =
  | 'start_learning_session'
  | 'learning_plan_request'
  | 'learning_progress_query'
  | 'course_rag_qa'
  | 'resource_generation'
  | 'default_chat'
  | 'general_chat'

interface IntentRoute {
  intent: IntentType
  confidence: number
  reason: string
  source: 'explicit' | 'context' | 'rule' | 'embedding' | 'small_model' | 'fallback'
  needs_clarification: boolean
  fallback_intent?: IntentType | null
  latency_ms: number
}
```

响应给前端时沿用已有 `route` 字段：

| 内部意图 | 响应 route | 行为 |
|---|---|---|
| `start_learning_session` | `learning_plan` 或 `default_chat` | 根据课程、路径、画像和当前时间生成今日学习入口或学习行动建议，不直接返回进度快照。 |
| `learning_plan_request` | `learning_plan` 或 `default_chat` | 生成短期学习计划、时间安排或下一步学习建议。 |
| `learning_progress_query` | `learning_progress` | 读取当前用户在课程下的真实掌握度、学习路径节点和学习事件。 |
| `course_rag_qa` | `course_rag_qa` | 走课程资料问答。 |
| `resource_generation` | `resource_generation` | 创建资源生成任务。 |
| `default_chat` / `general_chat` | `default_chat` | 走普通 ChatProvider。 |

### 6.3 混合路由分层

1. **显式字段优先**
   `action_type = resource_generation` 或 `intent_type = RESOURCE_GENERATION` 必须走资源生成；`mode = course_rag_qa` 或 `intent_type = COURSE_RAG_QA / KNOWLEDGE_QA` 必须走课程资料问答。

2. **业务规则层**
   优先处理权限、课程是否存在、知识库是否可用、资源生成是否有副作用、是否需要引用等业务约束。业务规则只决定“能不能执行”和“是否必须走某个能力”，不承担模糊语义泛化。

3. **高精度规则层**
   用于可解释、高确定性的场景，例如“我学到哪了”“我的学习进度怎么样”“课件里怎么定义梯度下降”“生成一套复习题”。资源生成产物词优先于学习进度词，避免“根据我的薄弱点出题”被误判为只看进度。

4. **多轮上下文**
   前端在 `clientContext.lastIntentRoute` 中传入上一轮响应 route。上下文只用于短追问，例如上一轮是 `learning_progress` 时，“那下一步呢”“还差什么”“该复习哪一节”可以继续识别为学习进度追问；“我要学”“今天学什么”不得因为上一轮 route 被无脑继承为学习进度查询。

5. **Intent Registry + 语义路由 Provider**
   后续应将正例、负例、阈值、风险等级、适用页面和可执行动作沉淀到 `examples.yaml` 或等价注册表。第一代开源内核优先接入 `semantic-router`，embedding 默认由 ModelGateway 云端 EmbeddingProvider 生成；只有 `semantic-router` 不可用或未返回候选时，才回退到 ModelGateway embedding 余弦相似度，供应商不可用或调用失败时再回退轻量本地实现。

6. **LLM Judge 结构化判别**
   当语义路由 top1 低于执行阈值、top1/top2 分差过小，或命中高风险动作时，可调用云端 ChatProvider 做结构化判别，输出固定 schema：`intent`、`confidence`、`slots`、`needs_clarification`、`reason`。LLM Judge 只在低置信场景触发，避免每轮对话都产生高额云端成本。

7. **置信度校准与灰度澄清**
   候选意图低于执行阈值、top1/top2 分差过小，或高风险意图证据不足时，不直接读取学情或创建任务，而是返回追问：“你是想开始今天的学习、查看学习进度，还是让我帮你制定学习计划？”对应响应 `availability.code = intent_clarification_required`。

### 6.4 示例

```text
mode = course_rag_qa
  → 必须走课程资料问答

actionType = resource_generation
  → 必须走资源生成

message = 我目前学到哪了
  → learning_progress_query

message = 我要学
  → start_learning_session

message = 今天我要学什么
  → start_learning_session / learning_plan_request

message = 帮我安排 30 分钟学习
  → learning_plan_request

message = 课件里怎么定义梯度下降
  → course_rag_qa

message = 根据我的薄弱点出五道练习题
  → resource_generation

上一轮 route = learning_progress，message = 那下一步呢
  → learning_progress_query

上一轮 route = learning_progress，message = 我要学
  → start_learning_session，不继承为 learning_progress_query

message = 解释一下梯度下降
  → default_chat
```

### 6.5 离线评测与反馈闭环

项目内置离线评测入口：

```bash
python backend/scripts/evaluate_intent_router.py
```

评测集由 `backend/app/services/ai/intent_router_eval.py` 生成，覆盖开始学习、学习计划、学习进度、课程资料问答、资源生成和普通 Chat。报告输出总体准确率、各意图 precision、recall、false positive、false negative 和 clarification rate。

商业化验收时，不能只看总体 accuracy。关键 guardrail 包括：

* `learning_progress_query` precision 应优先高于 recall，避免“我要学”“今天学什么”误触发个人进度读取。
* `resource_generation` false positive 必须极低，避免模糊输入误创建资源任务。
* `course_rag_qa` 必须区分“课件里怎么说”和“解释一下 X”，避免普通问题错误依赖文档库。
* `start_learning_session` 和 `learning_plan_request` 必须覆盖短句入口，承接用户真实学习动作。

用户或管理端可以通过 `/api/v1/ai/router-feedback` 记录路由反馈，字段包括原始问题、预测意图、期望意图、是否正确和备注。反馈写入 `ModelCallLog` 的 `intent_feedback` 能力日志，后续可沉淀为真实样例。

### 6.6 商业级演进路线

企业级项目不应把业务代码直接绑定到单一开源 router，而应保留自有 IntentRouter 接口，将开源能力作为可替换 Provider：

```text
HybridIntentRouter
  ├─ RuleRouter：显式模式、权限、课程上下文、高风险动作硬规则
  ├─ SemanticRouterProvider：semantic-router / 云端 Embedding / 本地轻量 Embedding
  ├─ LlmJudgeProvider：低置信时调用云端模型做结构化判别
  ├─ ClarificationPolicy：按风险等级生成澄清问题
  ├─ EvalHarness：离线评测与回归阈值
  └─ FeedbackStore：线上反馈、教师标注和错误案例沉淀
```

第一阶段以 `semantic-router` 作为语义路由内核，开发阶段默认通过 ModelGateway 调用云端 Embedding API，解决短句泛化和相似意图误判；第二阶段将意图样例、负例、阈值、风险等级和适用页面沉淀为 Intent Registry；第三阶段在管理端提供意图样例治理、阈值灰度、错误案例审核和路由日志回放。

### 6.7 推荐技术栈与复用边界

为避免重复造轮子，IntentRouter 2.0 应优先复用成熟开源能力，并通过项目自有 Provider 接口隔离实现细节。

| 技术 | 推荐用途 | 接入边界 |
|---|---|---|
| `semantic-router` | 第一代语义路由内核。用 Route / utterances 管理意图样例，返回候选 route 和置信度。 | 只在 `SemanticRouterProvider` 内部使用，不允许 `AiOrchestratorService` 直接依赖第三方 API。 |
| 云端 EmbeddingProvider | 开发阶段和企业部署的默认语义向量来源，降低本地显卡、模型缓存和镜像体积要求。 | 通过现有 ModelGateway 接入，路由层只消费统一 embedding 结果；密钥必须来自环境变量、`.env` 或安全密钥管理服务，禁止硬编码。 |
| `sentence-transformers` | 离线演示、断网兜底或私有化低成本部署的可选 Embedding 运行时。 | 只作为 encoder 备选项，不作为开发阶段默认方案，也不直接替代 Intent Registry、阈值策略和澄清策略。 |
| `BAAI/bge-small-zh-v1.5` 或同级小型中文 Embedding | 无云端 API 条件下的本地中文短句意图相似度召回备选。 | 仅作为降级候选；开发阶段不得为了路由能力强制下载或加载本地模型。 |
| `LangGraph` | 意图命中后的多 Agent 工作流编排，例如学习规划、资源生成、课程问答协作。 | 不把 LangGraph 当作意图分类器；它负责执行流，不负责训练样例和阈值治理。 |
| LLM Judge + Pydantic schema | 低置信、top1/top2 分差过小、高风险动作时做结构化判别。 | 只做兜底判别，不能每轮默认调用，避免成本失控。 |
| Redis / 进程内缓存 | 缓存样例 embedding、输入 embedding、短期路由结果和评测中间结果。 | 缓存不得改变路由事实来源；命中仍需记录 trace。 |
| `examples.yaml` / Intent Registry | 管理正例、负例、阈值、风险等级、页面适用范围和默认动作。 | 作为业务配置源，不把样例散落在代码常量中；必须同时支持后台可视化编辑和直接编辑配置文件。 |

当前阶段不建议直接引入 Rasa 或 Haystack 全量框架替换现有编排层。Rasa 更适合客服机器人式对话管理，Haystack 更适合作为完整 RAG / AI Pipeline 平台；如果未来要采用，也应作为独立 Provider 或 Pipeline 组件接入，而不是推翻 `AiOrchestratorService` 与自有 IntentRouter 接口。

必须明确的工程边界：

* 不要重新手写一套通用语义路由库；语义召回优先使用 `semantic-router`，不可用时才回退到统一 EmbeddingProvider 和轻量本地相似度。
* 开发阶段不要默认跑本地 Embedding 模型；默认走 ModelGateway 云端 Embedding API，本地模型只作为离线或私有化降级方案。
* 不要把意图样例硬编码在多个文件中；统一沉淀到 Intent Registry。
* 不要让大模型每轮都判断意图；只有低置信和高风险场景才进入 LLM Judge。
* 不要让第三方库决定业务动作；开源库只给候选意图和分数，最终执行由项目策略层决定。

### 6.8 Intent Registry 配置治理

IntentRouter 2.0 的意图样例、负例、阈值、风险等级、页面适用范围和默认动作必须采用“配置即代码 + 管理后台可视化”的双入口治理。

配置文件约定：

```text
backend/app/services/ai/intent/examples.yaml
  → 仓库内置默认样例和结构说明

storage/intent-router/intent_registry.yaml
  → 运行时活跃配置，路径可通过 INTENT_ROUTER_REGISTRY_PATH 覆盖
```

运行时读取优先级：

```text
INTENT_ROUTER_REGISTRY_PATH 指向的活跃配置
  > storage/intent-router/intent_registry.yaml
  > backend/app/services/ai/intent/examples.yaml 默认配置
```

当前实现将 `HybridIntentRouter` 保留为 HTTP 与 WebSocket 共用的门面类，内部委托以下模块：

```text
backend/app/services/ai/intent/types.py
backend/app/services/ai/intent/registry.py
backend/app/services/ai/intent/rules.py
backend/app/services/ai/intent/semantic_provider.py
backend/app/services/ai/intent/llm_judge.py
backend/app/services/ai/intent/clarification.py
backend/app/services/ai/intent/evaluator.py
backend/app/services/ai/intent/examples.yaml
```

`semantic_provider.py` 优先通过 `semantic-router` 的 Route / Router 内核召回候选意图，embedding 默认消费 ModelGateway 中启用的云端 EmbeddingProvider；当 `semantic-router` 包不可用、构建失败或未返回候选时，再用同一批 ModelGateway embedding 做余弦相似度回退；当开发环境没有可用 embedding provider 时，只使用 Registry 样例做轻量相似度兜底，不会下载或加载本地 embedding 模型。`llm_judge.py` 只在低置信、top1/top2 分差过小或高风险动作证据不足时触发，并通过 ModelGateway ChatProvider 输出 Pydantic schema。

管理后台必须提供可视化配置能力：

* 查看和编辑意图列表、正例、负例、执行阈值、澄清阈值、top1/top2 margin、风险等级和适用页面；
* 支持 YAML 原文编辑模式，便于批量维护；
* 支持导入、导出、校验、保存草稿、发布、回滚和热重载；
* 保存前运行 schema 校验和离线评测摘要，至少展示 precision、recall、false positive、false negative 和高风险意图误触发；
* 发布后写入 `AdminAuditLog`，记录操作者、变更摘要、旧版本、新版本、评测摘要和 traceId；
* 不得在 Intent Registry 中保存 API Key、Secret、Token，云端 Embedding 和 LLM Judge 凭证仍由 ModelGateway 或环境变量管理。

直接编辑文件也必须被支持：

* 开发者可以直接编辑 `INTENT_ROUTER_REGISTRY_PATH` 指向的 YAML 文件；
* 管理后台提供“重新加载配置”按钮，触发读取文件、校验 schema、预热样例 embedding、刷新缓存；
* 文件格式错误时不得替换当前已生效配置，应返回错误位置和字段名；
* 文件编辑和后台编辑应共享同一套校验器、评测器和发布流程，避免两套规则分叉；
* 容器化部署时，活跃配置文件应放在挂载卷中，避免写入只读镜像层。

### 6.9 不允许的设计

不允许让 Adapter 判断：

* 这个问题是不是要走 RAG；
* 这个任务是不是资源生成；
* 当前课程是否允许引用；
* 没命中文档时是否回退普通 Chat；
* 当前会话是否应该写入课程画像。

这些判断属于 `AiOrchestratorService`、`IntentRouter`、`CourseAiBindingService` 和业务策略层。

---

## 7. ProfileContextResolver

`ProfileContextResolver` 用于解析本次 AI 调用应该使用哪些画像。

### 7.1 输入

```ts
interface ResolveProfileContextInput {
  userId: string
  courseId?: string | null
  conversationId?: string
  taskType: 'chat' | 'resource_generation' | 'assessment' | 'path_planning'
  message?: string
  resourceType?: string
  pathNodeId?: string | null
  uploadedDocId?: string | null
}
```

### 7.2 输出

```ts
interface EffectiveProfileContext {
  scope: 'general' | 'course' | 'temporary_doc'
  userId: string
  courseId?: string | null
  globalProfile: GlobalLearningProfile
  courseProfile?: CourseLearningProfile | null
  sessionProfile: SessionProfile
  crossCourseHints?: CrossCourseHint[]
}
```

### 7.3 组合规则

有课程：

```text
全局画像 + 当前课程画像 + 当前会话画像 + 当前节点上下文
```

无课程：

```text
全局画像 + 当前会话画像 + 用户本轮意图
```

临时资料：

```text
全局画像 + 当前文档会话画像 + 临时资料上下文
```

---

## 8. CourseAiBindingService

课程绑定用于声明某门课程使用哪些 AI 能力。

### 8.1 推荐字段

```ts
interface CourseAiBinding {
  courseId: string
  chatProviderId?: string | null
  cloudRagProviderId?: string | null
  remoteKnowledgeBaseId?: string | null
  defaultAnswerMode: 'default_chat' | 'course_rag_qa'
  allowRagFallbackToChat: boolean
  requireCitationForCourseAnswer: boolean
  defaultUseCourseEvidenceForResource: boolean
  isEnabled: boolean
}
```

### 8.2 绑定原则

* ChatProvider 和 CloudRagProvider 分开绑定；
* 同一厂商可以同时提供两类能力，但系统内部必须按能力类型分开登记；
* CloudRagProvider 不能替代 ChatProvider；
* 没有课程时，使用系统默认 ChatProvider，不使用课程 CloudRagProvider；
* 课程资料问答必须检查课程绑定和远端知识库 ID。

---

## 9. ChatProvider

### 9.1 职责

* 普通对话；
* 通用学习规划；
* 资源生成正文；
* 学情画像分析；
* 错题归因总结；
* 多智能体角色推理；
* 内容改写和版本生成。

### 9.2 标准接口

```ts
interface ChatProvider {
  id: string
  type: 'chat'
  chat(input: ChatInput): Promise<ChatOutput>
  stream?(input: ChatInput): AsyncIterable<ChatChunk>
  testConnection(): Promise<ProviderHealth>
}
```

---

## 10. CloudRagProvider

### 10.1 职责

* 文档上传；
* 云端解析；
* 文档切分；
* 向量化；
* 状态同步；
* 检索测试；
* 基于课程资料问答；
* 返回引用来源；
* 为资源生成提取课程依据。

### 10.2 标准接口

```ts
interface CloudRagProvider {
  id: string
  type: 'cloud_rag'
  uploadDocument(input: UploadDocumentInput): Promise<UploadDocumentOutput>
  getDocumentStatus(remoteDocumentId: string): Promise<DocumentStatus>
  query(input: RagQueryInput): Promise<RagQueryOutput>
  retrieve?(input: RetrieveInput): Promise<RetrieveOutput>
  testConnection(): Promise<ProviderHealth>
}
```

---

## 11. CourseRagQaService

课程资料问答是显式模式，必须由用户明确选择。

### 11.1 调用链路

```text
用户点击“课程资料问答”
  ↓
输入课程资料相关问题
  ↓
POST /api/v1/ai/messages
  ↓
mode = course_rag_qa
  ↓
AiOrchestrator
  ↓
CourseRagQaService
  ↓
CloudRagProvider.query
  ↓
返回回答与引用来源
```

### 11.2 可用性检查

* 当前已选择课程；
* 课程已绑定 CloudRagProvider；
* 课程存在远端知识库 ID；
* 至少一个文档处于可问答状态；
* RAG 服务健康；
* 当前用户有访问课程资料权限。

### 11.3 未命中处理

如果课程资料没有命中足够依据，应提示：

```text
当前课程资料中没有找到足够依据。你可以切换为普通 AI 问答，我将基于通用知识解释。
```

开启 `requireCitationForCourseAnswer` 时，课程资料问答必须展示引用或明确说明未命中。

---

## 12. 资源生成中的课程依据提取

资源生成可以选择是否基于课程资料。

### 12.1 普通资源生成

```text
ResourceAgent + ChatProvider
```

### 12.2 带课程资料依据的资源生成

```text
ResourceAgent 判断 needCourseEvidence = true
  ↓
CloudRagProvider.retrieve / query 尝试获取依据
  ↓
命中依据：ChatProvider 根据依据生成资源正文
未命中依据：ChatProvider 基于课程上下文直接生成资源正文
  ↓
Verify 核验引用覆盖
  ↓
ArtifactCanvas 展示资源、引用和版本
```

### 12.3 降级策略

如果课程资料不可用或未命中可靠片段，资源生成不阻断，检索节点应记录降级说明并继续生成：

```text
未命中可用课程资料依据，已改用课程上下文和大模型直接生成，不返回模拟引用。
```

---

## 13. 结构化输出与工具调用纵深防御

所有需要机器消费的大模型输出都必须按生产级结构化治理链路处理。适用范围包括但不限于 Intent Router 的 LLM Judge、冷启动引导 JSON、画像抽取、资源大纲、阶段测评题、AI Rubric 评分、推荐解释、资源审核初检、多智能体阶段结果和工具调用参数。

### 13.1 分层原则

```text
提示词约束
  ↓
API 格式约束
  ↓
后端代码校验
  ↓
输出修复 / 重试
  ↓
标准化失败与降级
```

1. **提示词约束**：Prompt 必须说明任务目标、字段含义、完整 JSON 示例、边界场景、输出禁令和语言要求；结构化任务应调低温度，禁止 Markdown 代码块、额外解释和混合自然语言。
2. **API 格式约束**：模型供应商支持 `response_format`、JSON mode、JSON Schema、Function Calling、Tool Calling 或等价能力时，必须优先启用。Provider Adapter 应把项目内部 schema 映射到厂商协议，不能退化为仅靠自然语言提示。
3. **后端代码校验**：服务层必须执行清洗、解析、schema 校验和业务规则校验。校验内容至少覆盖必填字段、类型、枚举、数组长度、递归层级、字段间逻辑、引用约束、权限和安全策略。
4. **输出修复 / 重试**：校验失败时，优先把原始输出摘要、错误字段和校验失败原因回传给模型，要求其按同一 schema 重新输出；重试次数、超时和退避策略必须可配置或集中管理。
5. **标准化失败与降级**：连续失败后返回稳定错误码、可重试状态和安全用户提示。不得把不可解析 JSON、缺少标准答案的题单、未通过权限校验的工具参数或未核验引用的内容伪装成成功结果。

### 13.2 后端校验边界

结构化输出在通过后端校验前只能作为“不可信候选结果”。以下动作必须等校验通过后才能执行：

* 写入数据库或更新长期状态；
* 创建资源版本、测评题单、画像证据或推荐证据；
* 展示为可评分、可提交、可审核通过的正式内容；
* 调用具有副作用的工具；
* 向用户展示课程引用、质量分、安全结论或审核结论。

后端校验应优先使用 Pydantic、Zod、JSON Schema 或等价类型系统。复杂业务规则应放在服务层或专用 validator 中，不应散落在 Prompt、Adapter 或前端组件里。

### 13.3 工具调用安全模型

工具调用遵循“模型提出，后端裁决，服务执行”的边界：

```text
模型选择工具并生成参数
  ↓
后端校验工具白名单、权限和参数 schema
  ↓
服务层执行工具并捕获异常
  ↓
工具结果回填给模型或前端
  ↓
trace 记录工具名、参数摘要、耗时、状态和失败原因
```

要求：

* 工具名、参数 schema、权限范围和副作用等级必须由后端注册表定义，不能只写在 Prompt 中。
* 对写数据库、上传文件、发送通知、删除数据、调用外部服务等有副作用工具，必须校验登录态、课程权限、管理员权限、幂等键、限流和超时。
* 模型返回的工具参数不得直接拼接 SQL、文件路径、Shell 命令、URL 或第三方请求体；必须经过白名单、类型转换和业务校验。
* 工具执行失败应返回结构化错误，不把内部异常、密钥、完整堆栈或敏感参数暴露给模型和前端。
* 对高风险工具调用，IntentRouter 低置信时必须先澄清，不能自动执行。

### 13.4 Provider 与 Adapter 要求

ChatProvider 应在能力元数据中标明是否支持结构化输出、JSON Schema、Tool Calling、流式结构化输出和最大 schema 复杂度。Adapter 只负责协议映射和能力降级，不负责业务意图判断或业务合法性裁决。

当供应商不支持强结构化输出时，调用方必须显式记录降级原因，并启用更严格的后端解析、校验、修复和失败降级。新增模型供应商时，必须在连接测试或调用日志中暴露结构化能力检测结果，便于管理端判断该供应商能否承担资源生成、评分和工具调用任务。

### 13.5 Trace 与日志要求

结构化输出和工具调用必须记录：

* schema 名称、schema 版本和调用场景；
* 是否启用 API 结构化约束；
* 校验是否通过、失败字段和标准化错误码；
* 修复 / 重试次数、最终状态和耗时；
* 工具调用的工具名、权限上下文、参数摘要、幂等键、执行状态和异常分类。

日志只能保存必要摘要，禁止记录密钥、令牌、完整隐私数据、学生敏感答案原文或可复原的内部凭据。

---

## 14. Trace 与可观测性

每次 AI 调用都应记录 trace。

```ts
interface AiTrace {
  traceId: string
  userId: string
  courseId?: string | null
  conversationId?: string
  requestType: 'intent_route' | 'default_chat' | 'learning_progress' | 'course_rag_qa' | 'resource_generation' | 'rag_retrieve' | 'intent_feedback'
  providerType: 'intent_router' | 'chat' | 'cloud_rag' | 'resource_agent'
  providerId?: string
  modelOrKb?: string
  latencyMs: number
  tokenUsage?: TokenUsage
  success: boolean
  errorCode?: string
  errorMessage?: string
  citationCount?: number
  resourceTaskId?: string
  createdAt: string
  metaJson?: {
    intent?: string
    confidence?: number
    reason?: string
    source?: string
    candidates?: Array<{ intent: string; score: number; source: string }>
    needsClarification?: boolean
    fallbackIntent?: string | null
  }
}
```

Trace 用于：

* 会话排错；
* 成本统计；
* 意图路由命中原因分析；
* 低置信度澄清与灰度策略复盘；
* RAG 命中率统计；
* 资源生成成功率统计；
* 管理端调用日志；
* 质量分析；
* 安全审计。

---

## 15. 安全与回退策略

### 15.1 ChatProvider 不可用

普通 Chat 和资源生成不可用，提示：

```text
当前未配置 Chat 模型，暂时无法进行普通 AI 对话和资源生成。已配置的课程资料问答 / 云端 RAG 只能用于上传课程文档后的资料问答。请在网关中心添加 Chat 供应商后重试。
```

### 15.2 CloudRagProvider 不可用

课程资料问答不可用，但普通 Chat 和普通资源生成可用。

### 15.3 无课程状态

无课程状态下：

* 默认走 ChatProvider；
* 不调用课程 CloudRagProvider；
* 不写入课程画像；
* 资源默认是通用资源；
* 可提示用户选择课程以启用课程资料问答和学习路径。

### 15.4 低置信度意图

当 Hybrid Router 给出的业务候选意图置信度不足时：

* 不直接读取个人学习进度；
* 不直接创建资源生成任务；
* 不直接切到课程资料问答；
* 返回澄清问题，并记录 `intent_route` 日志；
* 前端仍以普通对话气泡展示澄清内容。

---

## 16. 验收标准

1. `/dashboard` 默认输入必须调用 ChatProvider，不得默认调用文档问答 API。
2. 只有用户显式选择“课程资料问答”时，才调用 CloudRagProvider。
3. 资源生成必须通过 ResourceAgent + ChatProvider。
4. 课程内资源生成默认先尝试检索课程依据；未命中可靠依据时必须降级为 ChatProvider 直接生成，不能伪造引用。
5. Adapter 不承担业务意图判断。
6. 无课程状态下普通对话和通用资源生成可用。
7. 无课程状态下课程资料问答不可用，并给出明确提示。
8. ChatProvider 为 0 时，普通对话和资源生成应提示不可用。
9. CloudRagProvider 未配置或文档未完成向量化时，课程资料问答应提示不可用。
10. 所有 AI 调用必须记录 trace，管理端可查看调用类型、供应商、成功状态和错误信息。
11. “我学到哪了”“我的学习进度怎么样”“下一步该学什么”应识别为 `learning_progress`，并基于真实学习数据回答。
12. “课件里怎么定义 X”应走课程资料问答；“解释一下 X”应默认走普通 Chat。
13. “根据我的薄弱点出题”应走资源生成，不应误判为只查看学习进度。
14. WebSocket 与 HTTP 入口必须共享同一套 Hybrid Router。
15. 管理端日志能筛选 `intent_route` 和 `intent_feedback`，并查看置信度、来源、候选意图和命中原因。
16. 离线评测脚本能输出样例数、准确率、precision、recall、false positive 和 false negative。
17. 机器消费的大模型输出必须启用结构化输出治理链路；供应商支持 JSON Schema 或 Tool Calling 时不得只依赖 Prompt。
18. 工具调用必须经过后端工具注册表、权限、参数 schema、幂等、限流和异常处理校验后再执行。
