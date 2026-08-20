# 挑战杯「揭榜挂帅」— 团队分工与协作完整方案

> 本文档基于 docs/10-competition-implementation-plan.md 优化调整，按三队重新拆分任务，明确每人的职责、产出、流程和代码提交规范。
> 
> 记录时间：2026-08-04

---

## 1. 团队组织架构

`
┌─────────────────────────────────────────────────────┐
│                   总队长（你）                        │
│              统筹管理 · 架构决策 · 质量把关             │
├──────────┬──────────┬──────────────────────────────┤
│   A 队    │   B 队    │   成队（文档/成果）            │
│  开发核心  │  开发辅助  │   文档 · PPT · 演示           │
├──────────┼──────────┼──────────────────────────────┤
│ 队长a（你）│ 副队长d   │   成员f（成队负责人）           │
│ 队员b     │ 队员e     │   成员g（文档辅助）             │
│ 队员c     │          │                               │
└──────────┴──────────┴──────────────────────────────┘
`

---

## 2. 各队角色定义总览

| 队伍 | 角色 | 代号 | 核心职责 | 技术栈 |
|------|------|------|---------|--------|
| **A队** | 队长a（你） | TL-A | 统筹管理、架构决策、代码审查、文档终审、演示准备 | 全栈视野，不写代码 |
| **A队** | 队员b | DEV-B | **后端开发主力** — 助学端后端 + AI编排 + 知识库 | Python/FastAPI/LangChain/SQLAlchemy |
| **A队** | 队员c | DEV-C | **前端开发主力** — 助学端页面 + 通用组件 + 沙箱UI | React/TS/Tailwind/shadcn/ui |
| **B队** | 副队长d | TL-D | 辅助管理 + **助教端后端** + 联调协调 | Python/FastAPI/LangChain |
| **B队** | 队员e | DEV-E | **助教端前端** — 助教端全部页面 | React/TS/Tailwind/shadcn/ui |
| **成队** | 成员f | DOC-F | **文档/PPT/材料总负责** | Markdown/PowerPoint/录屏工具 |
| **成队** | 成员g | DOC-G | 辅助文档 + 测试 + 素材收集 | Markdown/测试编写 |

> **你（队长a）不参与编码**，但负责审批 PR、把握架构方向、最终审核文档和演示准备。

---

## 3. 完整任务分工细化表

### 3.1 A队 — 队长a（你）的管理任务

> 你全程不做编码，但以下是你必须完成的"管理工作"：

| 阶段 | 任务 | 产出物 | 时间节点 |
|------|------|--------|---------|
| **第1周** | 在 GitHub 创建组织/仓库，初始化 main + develop 分支 | GitHub 仓库 | Day 1 |
| | 设置分支保护规则（develop 需要 PR 审查才能合并） | 仓库设置完成 | Day 1 |
| | 创建 GitHub Projects 看板（Backlog → To Do → In Progress → Review → Done）| 看板就绪 | Day 1 |
| | 将所有队员加入 Collaborators，分配权限 | 团队就绪 | Day 1 |
| | 编写 README 开发环境搭建指南，确保每个队员能跑通项目 | README 更新 | Day 2-3 |
| | 确定技术选型（Pyodide vs Docker、AI 模型供应商等）| 决策记录 | Day 2 |
| **第2-4周** | 每日早会（15分钟）：检查进度、协调阻塞 | 早会记录 | 每日 |
| | 审查所有 PR（Code Review），确保代码质量 | 合入 develop | 每日 |
| | 维护看板，调整优先级 | 看板更新 | 每日 |
| | 当队员有技术分歧时做架构决策 | 决策记录 | 按需 |
| **第5-6周** | 组织前后端联调会议 | 联调完成 | 第6周 |
| | 审查所有合入 develop→main 的 PR | 合入 main | 第6周末 |
| | 开始撰写比赛 PPT 大纲和系统说明书框架 | PPT大纲 | 第5周 |
| **第7-8周** | 带领全队进行系统回归测试 | 测试报告 | 第7周 |
| | 绘制系统架构图 + 多智能体流程图 | 图表文件 | 第7周 |
| | 导演 3 分钟演示视频录制 | 视频文件 | 第8周 |
| | 最终代码仓库整理 + 打包提交 | 提交包 | 第8周 |

---

### 3.2 A队 — 队员b（后端开发主力）

**角色定位**：负责助学端所有后端 API、AI 编排服务、知识库 RAG Pipeline、代码沙箱集成。

| 阶段 | 任务模块 | 具体产出 | 预估工时 |
|------|---------|---------|---------|
| **第1周** | 环境搭建 | 本地跑通 FastAPI + PostgreSQL，理解现有项目结构 | 8h |
| | 熟悉代码 | 阅读 backend/app/api/v1/routes/、services/、models/ | 8h |
| **第2周** | 多模态智能辅导后端 | 扩展 AI 编排服务，支持代码+图解混合输出（services/agent/）| 16h |
| | 学习行为跟踪引擎 | 新建事件采集 API + 存储 + 聚合服务 | 16h |
| **第3周** | 代码沙箱后端集成 | 集成 Pyodide（或 Docker 沙箱），包装为代码执行 API | 12h |
| | 画像证据链后端 | 扩展画像 API，新增证据抽取 + 溯源接口 | 12h |
| | 学科知识库构建 | 教材 PDF 导入 + 向量化 + 索引构建 | 8h |
| **第4周** | 自适应推送规则引擎 | 画像驱动 + 评分驱动的推送逻辑服务 | 16h |
| | 学习效果评估报告后端 | 评估报告生成 API + 数据聚合 | 12h |
| | LoRA 微调数据准备 | 整理 5000+ 条学科 QA 训练数据 | 8h |
| **第5周** | LoRA 微调 + 部署 | 训练 + vLLM 部署 + API 网关集成 | 20h |
| | RAG Pipeline 调优 | 分块策略/检索精度/引用溯源优化 | 12h |
| **第6周** | 多智能体协作增强 | 增强意图路由 + 多 Agent 编排逻辑 | 16h |
| | 全链路联调 | 与队员c（前端）联调助学端全流程 | 12h |
| **第7周** | Bug 修复 + 性能优化 | 修复联调发现的 Bug | 12h |
| **第8周** | 代码最终审查 + 提交准备 | 确保代码无遗留问题 | 8h |

**队员b 提交代码流程：**

`
1. git checkout develop && git pull origin develop
2. git checkout -b feat/backend/xxx       # 创建功能分支
3. # 开发 + 本地测试
4. git add .
5. git commit -m "feat(backend): 实现了xxx功能"
6. git push origin feat/backend/xxx
7. 在 GitHub 创建 Pull Request → target: develop
8. PR 描述写清楚：①做了什么 ②如何测试 ③影响范围
9. @队长a 请求审查
10. 队长a 审查通过后，在 GitHub 上合并
11. 切回 develop 拉取最新代码
`

---

### 3.3 A队 — 队员c（前端开发主力）

**角色定位**：负责助学端所有前端页面、通用组件库、代码沙箱 UI、多模态展示。

| 阶段 | 任务模块 | 具体产出 | 预估工时 |
|------|---------|---------|---------|
| **第1周** | 环境搭建 | 本地跑通 Vite + React，理解现有组件和页面结构 | 8h |
| | 熟悉代码 | 阅读 frontend/src/pages/、components/、docs/layout-spec.md | 8h |
| **第2周** | 多模态智能辅导前端 | 对话舱改造，支持代码块+图解流式混合展示 | 16h |
| | 学习行为跟踪前端 | 埋点 + 事件发送 + 学习行为仪表盘页面 | 16h |
| **第3周** | 代码沙箱前端组件 | 在线代码编辑器 + 运行按钮 + 结果输出区域 | 16h |
| | 画像证据链展示前端 | 画像详情页增强，展示证据链列表 | 12h |
| | 学习效果评估报告页面 | 评估报告展示页（图表 + 数据可视化）| 12h |
| **第4周** | 多智能体协作可视化前端 | Agent 工作流时间线可视化增强 | 16h |
| | AI 代码辅导对话界面 | 代码辅导专用对话界面 | 12h |
| **第5周** | 前端整体 UI 审查 | 检查所有页面符合 docs/layout-spec.md 规范 | 8h |
| **第6周** | 与队员b API 联调 | 对接所有新增后端 API | 16h |
| | 全链路联调 | 助学端完整流程走通 + Bug 修复 | 12h |
| **第7周** | Bug 修复 + UI 打磨 | 修复联调发现的问题 | 12h |
| **第8周** | 代码最终审查 + 提交准备 | 确保代码无遗留问题 | 8h |

**队员c 提交代码流程：**

`
1. git checkout develop && git pull origin develop
2. git checkout -b feat/frontend/xxx      # 创建功能分支
3. # 开发 + 本地测试
4. git add .
5. git commit -m "feat(frontend): 实现了xxx页面/组件"
6. git push origin feat/frontend/xxx
7. 在 GitHub 创建 Pull Request → target: develop
8. PR 描述附上页面截图说明（如有）
9. @队长a 请求审查
10. 队长a 审查通过后，在 GitHub 上合并
11. 切回 develop 拉取最新代码
`

---

### 3.4 B队 — 副队长d（助教端后端 + 辅助管理）

**角色定位**：辅助队长管理 + 负责助教端全部后端 API + 联调协调。

| 阶段 | 任务模块 | 具体产出 | 预估工时 |
|------|---------|---------|---------|
| **第1周** | 环境搭建 + 熟悉代码 | 跑通后端，阅读现有 ta.py 路由 + 已有 TA 数据模型 | 8h |
| | 助教端数据模型审查 | 检查已有 TA 模型是否完整（TaClass, TaLessonPlan, TaGradingRecord 等）| 4h |
| **第2周** | 智能备课后端 API | 教案生成、课件大纲生成、课堂活动推荐 API | 16h |
| | 作业批改后端 API | 客观题自动批阅、主观题 AI 辅助评阅、代码作业检测 API | 20h |
| **第3周** | 班级管理后端 API | 班级 CRUD + 学生关联 + 公告 API | 12h |
| | 助教端首页后端 | 统计数据聚合 API（卡片数据 + 任务列表 + 学情速览）| 12h |
| **第4周** | 学情诊断后端 API | 班级学情全景聚合 + 个体画像 API + 薄弱知识点识别 + AI 预警报告 | 20h |
| | AI 备课对话后端 | 对话式备课打磨功能 | 12h |
| **第5周** | 资源审核后端 | 学生资源列表 + 评价功能 API | 8h |
| | 与队员e 前端联调 | 对接助教端全部前端页面 | 16h |
| **第6周** | 全链路联调 | 助教端完整流程走通 + Bug 修复 | 12h |
| **第7周** | Bug 修复 | 修复联调发现的 Bug | 12h |
| **第8周** | 协助队长准备技术资料 | 提供 API 文档、数据流说明 | 8h |

**副队长d 额外管理职责：**
- 当队长a 不在时，代理日常管理
- 协调队员e（前端）与自己（后端）的 API 契约
- 每周向队长a 汇报 B 队进度

**副队长d 提交代码流程：**

`
1. git checkout develop && git pull origin develop
2. git checkout -b feat/backend-ta/xxx    # 创建功能分支
3. # 开发 + 本地测试
4. git add .
5. git commit -m "feat(backend-ta): 实现了xxx功能"
6. git push origin feat/backend-ta/xxx
7. 在 GitHub 创建 Pull Request → target: develop
8. @队长a 请求审查
9. 队长a 审查通过后合并
10. 切回 develop 拉取最新代码
`

---

### 3.5 B队 — 队员e（助教端前端）

**角色定位**：负责助教端全部前端页面开发。

| 阶段 | 任务模块 | 具体产出 | 预估工时 |
|------|---------|---------|---------|
| **第1周** | 环境搭建 + 熟悉代码 | 跑通前端，阅读现有 TA 页面源码 + docs/layout-spec.md | 8h |
| | 助教端路由规划 | 确认助教端路由结构 + 页面框架搭建 | 4h |
| **第2周** | 智能备课前端页面 | 备课工作台：教案生成、课件大纲生成、活动推荐 UI | 20h |
| | 作业批改前端页面 | 批改台：客观题/主观题/代码作业批改界面 + 列表 + 详情 | 20h |
| **第3周** | 班级管理前端页面 | 班级管理全页面（创建/编辑/删除/学生列表）| 12h |
| | 助教端工作台首页 | 统计卡片 + 任务列表 + 学情速览 UI | 12h |
| **第4周** | 学情诊断前端页面 | 诊断看板（班级全景 + 个体画像 + 薄弱识别 + 预警列表 + 报告导出）| 20h |
| | AI 备课对话前端 | 对话式备课交互界面 | 12h |
| **第5周** | 资源审核前端页面 | 学生资源列表 + 评价 UI | 8h |
| | 公告管理前端页面 | 公告发布 + 推送管理 UI | 8h |
| | 与副队长d API 联调 | 对接所有助教端后端 API | 16h |
| **第6周** | 全链路联调 | 助教端完整流程走通 + Bug 修复 | 12h |
| **第7周** | Bug 修复 + UI 规范审查 | 确保所有页面符合 layout-spec.md | 12h |
| **第8周** | 代码最终审查 + 提交准备 | 确保代码无遗留问题 | 8h |

**队员e 提交代码流程：**

`
1. git checkout develop && git pull origin develop
2. git checkout -b feat/frontend-ta/xxx   # 创建功能分支
3. # 开发 + 本地测试
4. git add .
5. git commit -m "feat(frontend-ta): 实现了xxx页面"
6. git push origin feat/frontend-ta/xxx
7. 在 GitHub 创建 Pull Request → target: develop
8. PR 描述附上页面截图（如有）
9. @副队长d @队长a 请求审查
10. 队长a 审查通过后合并
11. 切回 develop 拉取最新代码
`

---

### 3.6 成队 — 成员f（文档/材料总负责人）

**角色定位**：全程负责非代码类比赛产出物，包括文档、PPT、演示材料、用户测评。

| 阶段 | 任务模块 | 具体产出 | 预估工时 |
|------|---------|---------|---------|
| **第1周** | 理解项目 | 阅读所有 docs/ 文档，理解产品定位和功能全貌 | 6h |
| | 文档模板准备 | 为比赛各类文档建立模板框架 | 4h |
| **第2-4周** | 跟踪开发进度 | 每周与各队沟通，收集功能截图和关键数据 | 每周3h |
| | 素材积累 | 录制开发过程中的功能 demo 片段（为演示视频准备素材）| 持续 |
| **第5周** | 系统说明书初稿 | 按比赛要求撰写需求+技术+测试全流程文档 | 20h |
| | PPT 初稿 | 建立 PPT 内容框架 + 初版内容填充 | 16h |
| **第6周** | 伦理与安全合规声明 | 撰写并准备签字文档 | 8h |
| | 用户测评准备 | 准备测评问卷 + 2名以上真实用户试用安排 | 8h |
| **第7周** | 系统说明书终稿 | 根据开发完成情况更新完善 | 12h |
| | PPT 终稿 | 整合全部内容 + 配合队长审查修改 | 12h |
| | 效果验证报告 | 测试数据 + 对比分析 + 截图 | 8h |
| **第8周** | 配合演示视频 | 协助队长录制视频素材、旁白字幕 | 8h |
| | 文档打包 | 所有比赛提交文档最终审核 + 格式统一 | 4h |

**成员f 提交文档流程（文档也走 Git）：**

`
1. git checkout develop && git pull origin develop
2. git checkout -b feat/docs/xxx           # 创建文档分支
3. 将文档放入 docs/submit/ 目录
4. git add .
5. git commit -m "docs: 完成了xxx文档"
6. git push origin feat/docs/xxx
7. 创建 PR → target: develop
8. @队长a @副队长d 请求审查
9. 审查通过后合并
`

---

### 3.7 成队 — 成员g（文档辅助）

**角色定位**：协助成员f，负责测试、素材、排版等辅助工作。

| 工作项 | 说明 | 预估工时（全程）|
|--------|------|---------------|
| 测试用例编写 | 编写系统测试用例 + 执行测试并记录结果 | 20h |
| 素材收集 | 截取功能截图、录制功能短视频、收集用户反馈 | 12h |
| 文档排版 | 统一文档格式、生成目录、导出 PDF | 8h |
| 合规检查 | 检查伦理声明、开源许可证、第三方依赖合规 | 6h |
| 数据整理 | 整理测试数据、评分对照表、功能清单 | 8h |

**成员g 提交代码流程：**

`
1. git checkout develop && git pull origin develop
2. git checkout -b feat/docs-aux/xxx      # 创建文档辅助分支
3. 将文件放入 docs/ 对应目录
4. git add .
5. git commit -m "docs: 完成了xxx素材/测试"
6. git push origin feat/docs-aux/xxx
7. 创建 PR → target: develop
8. @成员f @队长a 审查
`

---

## 4. 代码提交与合并完整规范

### 4.1 GitHub 仓库结构

`
📦 repo-name/
├── main/                    # 生产分支 — 比赛最终提交版本
├── develop/                 # 开发集成分支 — 日常开发基础
├── feat/backend/xxx/        # 队员b 的功能分支
├── feat/frontend/xxx/       # 队员c 的功能分支
├── feat/backend-ta/xxx/     # 副队长d 的功能分支
├── feat/frontend-ta/xxx/    # 队员e 的功能分支
├── feat/docs/xxx/           # 成员f 的文档分支
├── feat/docs-aux/xxx/       # 成员g 的文档辅助分支
└── fix/xxx/                 # 任何人修 Bug 的分支
`

### 4.2 分支命名规范

| 前缀 | 使用者 | 示例 |
|------|--------|------|
| feat/backend/ | 队员b | feat/backend/learning-behavior-tracking |
| feat/frontend/ | 队员c | feat/frontend/code-sandbox-ui |
| feat/backend-ta/ | 副队长d | feat/backend-ta/lesson-planning-api |
| feat/frontend-ta/ | 队员e | feat/frontend-ta/diagnosis-dashboard |
| feat/docs/ | 成员f | feat/docs/system-manual |
| feat/docs-aux/ | 成员g | feat/docs-aux/test-cases |
| fix/ | 任何人 | fix/dashboard-crash |

### 4.3 GitHub 分支保护设置

队长a 在仓库 Settings > Branches 中设置：

`
Branch: develop
- ✅ Require a pull request before merging
- ✅ Require approvals（至少 1 人审查）
- ✅ Dismiss stale pull request approvals when new commits are pushed

Branch: main
- ✅ Require a pull request before merging
- ✅ Require approvals（至少 1 人审查）
- ✅ Do not allow bypassing the above settings
`

### 4.4 PR 审查清单（队长a 审查时使用）

每条 PR 合并前必须逐项检查：

`
□ 代码能正常编译/运行（无语法错误）
□ 遵循项目现有代码风格和架构
□ 前端页面符合 docs/layout-spec.md 规范
□ 注释使用简体中文（按 AGENTS.md 要求）
□ API 有基本的错误处理和输入校验
□ 没有硬编码密钥、Token、密码或敏感信息
□ 没有引入不必要的第三方依赖
□ PR 描述清晰说明了改动内容和测试方式
□ 没有破坏已有功能（回归检查）
□ 文档同步更新（如果本次改动涉及）
`

### 4.5 日常同步（避免冲突）

`
# 每个队员每天开始工作前：
git checkout develop
git pull origin develop               # 拉取队友的最新代码

# 如果功能分支开发了几天还没合入：
git checkout feat/xxx/xxx
git rebase origin/develop              # 把你的改动 rebase 到最新的 develop 上
# 如果有冲突，Git 会提示 → 解决冲突 → git rebase --continue
git push origin feat/xxx/xxx --force-with-lease
`

---

## 5. 使用 AI 辅助（Superpower 提效策略）

每个队员可用 AI 助手（Codex/Claude/Cursor 等）提升开发效率。

### 5.1 队员b（后端）使用 AI

**场景：新增后端路由**

`
在智课项目后端新增一个路由文件。
项目使用 FastAPI + SQLAlchemy + Pydantic。
现有路由风格参考 backend/app/api/v1/routes/ 下的文件。

需求：[描述具体功能]

要求：
- 路由文件放在 backend/app/api/v1/routes/
- 业务逻辑放在 backend/app/services/xxx.py
- 数据模型放在 backend/app/models/xxx.py
- 路由前缀使用 /api/v1/xxx
- 认证依赖使用 Depends(get_current_user)
- 数据库依赖使用 Depends(get_db)
- 注释使用简体中文
- 参考现有路由文件 xxx 的写法
`

**场景：新增 AI 编排能力**

`
在智课项目 backend/app/services/agent/ 下扩展多智能体编排。
现有编排逻辑参考 services/agent/ 下的文件。
需要新增一个 Agent 节点，功能：[描述]。
Agent 需要支持：
- 输入：用户消息 + 上下文
- 处理：调用 LLM + 知识库检索
- 输出：结构化结果
- 引用溯源
`

### 5.2 队员c + 队员e（前端）使用 AI

**场景：新增页面**

`
在智课项目前端新增一个页面。
项目使用 React + TypeScript + Tailwind + shadcn/ui。

页面路径：/xxx
页面内容：[描述]
后端 API 地址：/api/v1/xxx

要求：
- 页面头部使用 PageHeader 组件，遵循 docs/layout-spec.md 规范
- 标题使用简体中文
- 页面文件放在 frontend/src/pages/xxx/
- 子组件放在 frontend/src/components/xxx/
- API 请求放在 frontend/src/api/xxx.ts
- 参考现有页面 xxx 的实现风格
`

**场景：实现表单/列表**

`
在智课前端实现一个[表单/列表]功能。
使用 shadcn/ui 的 [Form/Table] 组件。
表单字段：[列出字段]
列表需要支持：搜索、分页、排序。
参考现有 [xxx 页面] 的实现。
`

### 5.3 副队长d（后端+管理）使用 AI

**场景：数据聚合/统计 API**

`
在 backend/app/services/ 下新增一个数据统计聚合服务。
需要从 [表A]、[表B] 中聚合数据，按 [班级/课程/时间段] 分组。
使用 SQLAlchemy 查询 + 聚合函数。
返回 Pydantic schema。
参考现有 xxx 服务的实现。
`

### 5.4 成员f/g（文档）使用 AI

**场景：写文档/PPT 大纲**

`
为智课比赛项目撰写 [xxx 章节]。
项目定位：[一句话描述]
核心功能：[列举]
技术栈：React + FastAPI + PostgreSQL + LangChain
项目目标：挑战杯"揭榜挂帅"比赛，冲刺高分
风格要求：专业、正式、面向比赛评审专家
字数：[预估字数]
`

### 5.5 队长a（你）使用 AI 做代码审查

**场景：审查 PR**

`
以下是一个 Pull Request 的代码改动，请帮我做代码审查。
重点关注：
1. 安全风险（SQL注入、密钥泄露、权限缺失）
2. 是否符合项目现有代码风格
3. 潜在的 Bug
4. 注释是否使用简体中文
5. 是否引入了不必要的依赖
6. 是否有更好的实现方式

[粘贴 Diff]
`

**场景：修改前端页面使其符合 layout-spec**

`
以下是一个前端页面的代码片段。
项目要求头部必须使用 PageHeader 组件，遵循 docs/layout-spec.md 规范。
帮我修改使其符合规范。

[粘贴代码]
`

---

## 6. 团队协作规则

### 6.1 沟通节奏

| 频次 | 形式 | 时长 | 内容 | 参与人 |
|------|------|------|------|--------|
| **每日** | 站会（微信群/飞书） | 15分钟 | 昨天做了什么、今天做什么、有什么阻塞 | 全队 |
| **每周一** | 周会 | 30分钟 | 上周回顾 + 本周计划 + 风险评估 | 全队 |
| **按需** | 技术讨论会 | 不限 | API 契约对齐、联调问题讨论 | 相关队员 + 队长 |

### 6.2 API 契约先行原则

当队员e（前端）开发时，后端 API 可能还没写好。处理方式：

`
1. 副队长d 先写 API 契约：定义请求/响应 JSON Schema
2. 队员e 在 frontend/src/mocks/ 下模拟 API 返回，不阻塞开发
3. 后端开发完成后，前端替换 Mock 为真实 API 调用
4. 队长a 负责确保 API 契约在开发前已对齐
`

### 6.3 冲突处理

| 问题类型 | 处理方式 |
|---------|---------|
| Git 代码冲突 | 先推代码的人负责解决冲突，解决不了找相关队员一起处理 |
| 接口字段不一致 | 相关队员即时沟通对齐，必要时通知队长a |
| 技术方案分歧 | 队长a 组织讨论并最终拍板 |
| 进度风险 | 队员尽早暴露风险 → 队长a 调整优先级或重新分配 |

---

## 7. 比赛时间轴与里程碑

### 甘特图

`
周次    第1周    第2周    第3周    第4周    第5周    第6周    第7周    第8周
─────  ─────── ─────── ─────── ─────── ─────── ─────── ─────── ───────
A队长a  ██基建  ██管理  ██管理  ██管理  ██联调  ██文档  ██测试  ██提交
A队员b  ██熟悉  ██后端  ██后端  ██后端  ██微调  ██联调  ██修复  ██收尾
A队员c  ██熟悉  ██前端  ██前端  ██前端  ██联调  ██联调  ██修复  ██收尾
B副队d  ██熟悉  ██后端  ██后端  ██后端  ██联调  ██联调  ██修复  ██收尾
B队员e  ██熟悉  ██前端  ██前端  ██前端  ██联调  ██联调  ██修复  ██收尾
成员f   ██了解  ██素材  ██素材  ██素材  ██说明  ██PPT   ██终稿  ██打包
成员g   ██了解  ██测试  ██测试  ██测试  ██数据  ██合规  ██审核  ██打包
`

### 关键里程碑

| 里程碑 | 截止时间 | 验收标准 | 负责人 |
|--------|---------|---------|--------|
| M1: 环境就绪 | 第1周末 | 所有队员本地跑通项目 | 队长a |
| M2: 助学端核心功能完成 | 第4周末 | 对话+学习路径+画像可正常使用 | 队员b + 队员c |
| M3: 助教端核心功能完成 | 第4周末 | 备课+批改+学情诊断可用 | 副队长d + 队员e |
| M4: 全链路联调完成 | 第6周末 | 双端口端到端流程无重大 Bug | 队长a 组织 |
| M5: 全部文档完成 | 第7周末 | 终稿通过队长终审 | 成员f |
| M6: 比赛提交 | 第8周 | 全部材料打包完成 | 队长a |

---

## 8. 队长a 每周操作清单

### 每周一
`
□ 更新 GitHub Projects 看板（把上周 Done 的任务归档）
□ 把本周要做的任务从 Backlog 移到 To Do
□ 开周会：确认本周每个人的任务和优先级
□ 检查每个队员是否已拉取最新 develop 代码
`

### 每周三
`
□ 检查每个队员是否有至少一个 In Progress 的任务
□ 检查是否有超过 2 天未被审查的 PR（优先审查）
□ 询问是否有技术阻塞需要你决策
`

### 每周五
`
□ 统计本周合入 develop 的 PR 数量和内容
□ 对比实际进度 vs 计划进度，偏差过大则调整下周计划
□ 更新看板（标记完成、调整优先级）
□ 记录本周周报要点（同步给全队）
`

### 关键检查点

| 检查点 | 你该关注什么 |
|--------|------------|
| **队员b** | 后端 API 是否按进度完成？AI 服务质量是否达标？| 
| **队员c** | 前端页面是否符合 layout-spec？联调是否顺利？|
| **副队长d** | 助教端后端 API 进度？是否做好 API 契约供队员e 使用？|
| **队员e** | 助教端页面是否按设计完成？是否因为无 API 而阻塞？|
| **成员f** | 文档是否跟上开发进度？PPT 框架是否搭建好？|
| **成员g** | 测试用例是否覆盖核心功能？素材是否备齐？|

---

## 9. 附录：快速命令速查

### 首次搭建项目

`ash
git clone https://github.com/xxx/xxx.git
cd xxx

# 后端环境
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 前端环境
cd frontend
npm install
`

### 日常 Git 命令

`ash
# 拉取最新
git checkout develop
git pull origin develop

# 创建新分支
git checkout -b feat/xxx/yyy

# 查看状态
git status

# 提交
git add .
git commit -m "feat(xxx): 做了什么"
git push origin feat/xxx/yyy

# 同步 develop（当功能分支开发了几天）
git fetch origin
git rebase origin/develop
# 解决冲突 → git rebase --continue
git push origin feat/xxx/yyy --force-with-lease

# 切回 develop 并拉取（PR 合并后）
git checkout develop
git pull origin develop

# 删除本地功能分支（已合并后）
git branch -d feat/xxx/yyy
`

---

## 10. 总结：一句话概括每个人的职责

| 角色 | 一句话概括 |
|------|-----------|
| **队长a（你）** | 不写代码，但管好架构、进度、审查、文档和演示 |
| **队员b** | 专攻助学端后端，管好 AI 编排和知识库 |
| **队员c** | 专攻助学端前端，管好页面和组件 |
| **副队长d** | 专攻助教端后端 + 辅助管理，管好 API 契约 |
| **队员e** | 专攻助教端前端，管好所有 TA 页面 |
| **成员f** | 专攻文档/PPT/材料，管好比赛提交物 |
| **成员g** | 辅助成员f，管好测试和素材收集 |

---

> 本文档由队长a 维护，如有角色调整或任务变动需及时更新并通知全队。
