# 团队上手指南

## 项目概览

本项目基于「智课 AI 个性化学习工作台」改造为面向**计算机科学与人工智能学科**的**双端口智能教学平台**：

- **助学端（学生端口）**：AI 驱动的个性化学习工作台（浏览器访问 `/dashboard`）
- **助教端（TA/助教端口）**：AI 辅助的教学管理工作台（浏览器访问 `/ta/dashboard`）

> 两个端口共享同一后端底座（学科垂类大模型 + RAG 知识库 + 多智能体引擎）

## 技术栈速查

| 技术 | 用途 | 关键文件/目录 |
|------|------|-------------|
| React 18 + TypeScript | 前端框架 | `frontend/src/` |
| Vite 6 | 构建工具 | `frontend/vite.config.ts` |
| Tailwind CSS 3 | CSS 框架 | `frontend/tailwind.config.ts` |
| Zustand | 状态管理 | `frontend/src/stores/*.store.ts` |
| TanStack Query | 数据获取 | `frontend/src/api/` |
| React Router 7 | 路由 | `frontend/src/app/router.tsx` |
| FastAPI + Python 3.12 | 后端框架 | `backend/app/` |
| SQLAlchemy 2.0 | ORM | `backend/app/models/*.py` |
| Alembic | 数据库迁移 | `backend/alembic/` |

## 团队分工与职责

```
队长（你）
  ├─ 第1-2周：搭建双端口脚手架（已完成）
  ├─ 第3-6周：带领助学端开发（你 + 成员B + 成员C）
  │   ├─ 你：助学端前端（对话舱增强、代码沙箱、多模态辅导）
  │   ├─ 成员B：助学端后端（多模态API、行为跟踪、评估报告）
  │   └─ 成员C：AI集成（LoRA微调、RAG知识库、推选引擎）
  └─ 第7-8周：架构图绘制 + 联调 + 评审支持

副队长
  └─ 第3-6周：带领助教端开发（副队长 + 成员D）
      ├─ 副队长：助教端前端所有页面
      └─ 成员D：助教端后端所有API

成员E（文档）
  └─ 第1-8周：全程文档 + 第7-8周：PPT/视频/用户反馈
```

## 如何开始开发

### 1. 后端开发

```bash
cd backend
.venv\Scripts\activate    # 激活虚拟环境
alembic upgrade head       # 运行最新迁移（含新 TA 表）
python run_dev.py          # 启动后端（localhost:8001）
```

### 2. 前端开发

```bash
cd frontend
corepack pnpm dev          # 启动前端（localhost:5173）
```

### 3. 查看 API 文档

后端启动后访问：http://localhost:8001/docs（Swagger UI）

## 新人学习路线（团队不熟悉 React/FastAPI 时）

### 前端学习（预计3-5天）

1. **React 基础**（1天）：阅读官方文档的"Describing the UI"和"Adding Interactivity"
2. **TypeScript 基础**（1天）：类型、接口、泛型
3. **Tailwind CSS**（半天）：实用优先的 CSS 框架
4. **项目现有页面**（1天）：阅读 `frontend/src/pages/dashboard/DashboardPage.tsx` 和 `frontend/src/app/WorkspaceLayout.tsx`
5. **Zustand + API 调用**（半天）：阅读 `frontend/src/stores/session.store.ts` 和 `frontend/src/api/client.ts`

### 后端学习（预计3-5天）

1. **FastAPI 基础**（1天）：阅读官方文档的"First Steps"和"Path Parameters"
2. **SQLAlchemy 2.0**（1天）：阅读项目现有模型 `backend/app/models/user.py` 和 `backend/app/models/course.py`
3. **Alembic**（半天）：了解迁移机制
4. **项目现有 API**（1天）：阅读 `backend/app/api/v1/routes/auth.py` 和 `backend/app/api/v1/routes/courses.py`
5. **依赖注入**（半天）：理解 Depends(get_db) 和 Depends(get_current_user)

## 开发约定

- **Git 提交**：使用中文描述，格式 `[模块] 做了什么`，如 `[TA备课] 完成教案生成API`
- **代码注释**：说明性注释用简体中文
- **API 设计**：RESTful 风格，路径用 kebab-case
- **组件命名**：PascalCase，文件同名
- **状态管理**：全局状态用 Zustand store，API 数据用 TanStack Query
- **路由添加**：在 `frontend/src/app/router.tsx` 中添加新路由

## 文件索引

### 助学端核心文件
| 文件 | 用途 |
|------|------|
| `frontend/src/pages/dashboard/DashboardPage.tsx` | 学生端首页（AI 对话舱） |
| `frontend/src/app/WorkspaceLayout.tsx` | 学生端布局 |
| `backend/app/api/v1/routes/ai.py` | AI 对话 API |
| `backend/app/services/ai/orchestrator.py` | AI 编排服务 |

### 助教端核心文件（新增）
| 文件 | 用途 |
|------|------|
| `frontend/src/app/TAGate.tsx` | 助教端权限守卫 |
| `frontend/src/app/TaLayout.tsx` | 助教端布局 |
| `frontend/src/stores/ta.store.ts` | 助教端状态管理 |
| `frontend/src/pages/ta/*.tsx` | 7个助教端页面 |
| `backend/app/api/v1/routes/ta.py` | 助教端 API |
| `backend/app/models/ta_*.py` | 6个助教端数据模型 |
| `backend/alembic/versions/0045_ta_portal_base.py` | 数据库迁移 |

## 常见问题

**Q: 前端启动报错？**
A: 确保已执行 `cd frontend && corepack pnpm install`

**Q: 数据库迁移失败？**
A: 确认 PostgreSQL 已启动，执行 `alembic upgrade head` 或 `alembic upgrade 0045`

**Q: 新增 API 需要登录？**
A: 使用 `Depends(get_current_user)` 会自动校验 JWT Token

**Q: 如何添加新页面？**
A: 1. 在 `frontend/src/pages/` 下创建页面组件 2. 在 `router.tsx` 中添加路由
