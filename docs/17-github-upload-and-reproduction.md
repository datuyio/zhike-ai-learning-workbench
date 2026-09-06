# GitHub 上传清单与项目复刻指南

> 更新日期：2026-08-20  
> 远程仓库：`https://github.com/datuyio/zhike-ai-learning-workbench.git`  
> 当前状态：以下为整理后的推荐上传范围，尚未执行最终推送。

## 1. 总原则

- 上传源代码、文档、脚本、配置模板和可复现知识库的许可语料。
- 不上传密钥、数据库数据、虚拟环境、依赖目录、构建产物和日志；模型权重按你的要求随仓库上传。
- 本地知识库的向量可以在新环境通过原始 Markdown 重新生成，因此不需要上传 PostgreSQL 中的向量数据。
- 上传前不要使用 `git add .`，应按照下方清单逐项添加，避免误传 `.env` 等敏感文件。

## 2. 建议上传清单

| 类别 | 内容 | 说明 |
|---|---|---|
| 前端源码 | `frontend/src/`、`frontend/public/`、`frontend/index.html`、`frontend/vite.config.ts`、`frontend/package.json`、`frontend/pnpm-lock.yaml`、`frontend/pnpm-workspace.yaml` | 前端完整源码和锁文件 |
| 前端配置 | `frontend/tsconfig*.json`、`frontend/eslint.config.*`、`frontend/tailwind.config.*`、`frontend/vitest.config.ts`、`frontend/playwright.config.*` | 类型检查、测试和构建配置 |
| 后端源码 | `backend/app/`、`backend/alembic/`、`backend/db/`、`backend/tests/`、`backend/scripts/` | FastAPI 应用、迁移、数据库初始化、测试和工具脚本 |
| 后端配置 | `backend/requirements.txt`、`backend/pyproject.toml`、`backend/run_dev.py`、`backend/Dockerfile`、`backend/.dockerignore`、`backend/SETUP.md` | 依赖、运行入口和容器配置 |
| 根目录工程配置 | `docker-compose.yml`、`.gitignore`、`.env.example`、`start-dev.bat`、`scripts/start-dev.ps1` | 一键启动和开发环境模板 |
| 文档 | `README.md`、`docs/` | 产品说明、功能设计、验收记录和复刻指南 |
| 课程体系数据 | `frontend/src/data/curriculumCatalog.json` | 课程、阶段和资料知识点目录 |
| 本地知识库清单 | `storage/knowledge-sources/manifest.json` | 语料来源、许可证、路径、哈希和大小 |
| 本地知识库语料 | `storage/knowledge-sources/{ai-ml,algorithms,cs-foundations,data-system,llm-agents,supplement,web-engineering}/**` | 仅上传许可证明确、允许再分发的 Markdown/MDX 文件，保留原仓库 LICENSE |
| 本地 Embedding 模型权重 | `backend/storage/models/models--BAAI--bge-small-zh-v1.5/` | 约 92 MB，最大文件约 91.4 MB，在 GitHub 单文件 100 MB 限制内 |
| 已存在的 LoRA 增量权重 | `deploy/inference/lora_weights_final/` | 约 88 MB，已在 Git 跟踪；如需继续保留可上传，但优先考虑放到 GitHub Release |
| README 引用的截图 | `screenshots/` | 约 2.3 MB，避免文档图片失效 |

## 3. 不上传清单

| 类别 | 内容 | 原因 |
|---|---|---|
| 环境密钥 | `.env`、`backend/.env`，以及任何包含真实密钥、Token、数据库密码的文件 | 防止凭据泄露；只上传 `.env.example` |
| 向量与数据库数据 | PostgreSQL `zhike_workshop` 中的 `documents`、`document_chunks`、`users`、`learning_paths` 等表 | 数据库不是源码，新环境可通过脚本重建 |
| Python 虚拟环境 | `backend/.venv/`、`.venv/`、`venv/` | 依赖应通过 `requirements.txt` 安装 |
| 前端依赖与构建产物 | `frontend/node_modules/`、`frontend/dist/`、`frontend/dist-verify/` | 应通过 `pnpm-lock.yaml` 安装和构建 |
| 沙箱依赖 | `backend/sandbox-service/node_modules/` | 应通过 `npm install` 安装 |
| 临时与测试产物 | `*.log`、`*.pyc`、`__pycache__/`、`.pytest-*`、`.ruff_cache/`、`test-results/`、`playwright-report/` | 不属于项目源码 |
| 本机辅助目录 | `.codex/`、`.agents/`、`.ta-portal-src/`、`.pgvector-src/`、`.tmp-*.tar.gz` | 本地开发辅助内容，不建议发布 |
| 未授权或许可证不明确的语料 | `NOASSERTION`、`UNLICENSED`、无许可证声明的内容 | 避免知识产权和再分发风险；导入脚本默认跳过这些内容 |

## 4. 上传前需要处理的 `.gitignore`

当前 `.gitignore` 已经忽略 `storage/` 和 `backend/storage/`。如果要把知识库语料和 Embedding 模型权重纳入上传范围，需要按下面的白名单方式调整：

```gitignore
storage/*
!storage/knowledge-sources/
storage/knowledge-sources/*
!storage/knowledge-sources/manifest.json
!storage/knowledge-sources/ai-ml/
!storage/knowledge-sources/algorithms/
!storage/knowledge-sources/cs-foundations/
!storage/knowledge-sources/data-system/
!storage/knowledge-sources/llm-agents/
!storage/knowledge-sources/supplement/
!storage/knowledge-sources/web-engineering/
```

注意：不要直接放开整个 `backend/storage/`。如果要上传 Embedding 模型，可以把现有 `backend/storage/` 忽略规则改成白名单形式：

```gitignore
backend/storage/*
!backend/storage/models/
backend/storage/models/*
!backend/storage/models/models--BAAI--bge-small-zh-v1.5/
```

这样只放开模型权重目录，`backend/storage/provider-icons`、`backend/storage/site-assets` 等其他本地产物仍不会进入 Git。

## 5. 推荐上传命令（不执行 `git add .`）

```bash
git add .env.example .gitignore docker-compose.yml README.md start-dev.bat
git add scripts docs frontend/src frontend/public frontend/index.html
git add frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml
git add frontend/tsconfig.json frontend/vite.config.ts frontend/vitest.config.ts
git add backend/app backend/alembic backend/db backend/tests backend/scripts
git add backend/requirements.txt backend/pyproject.toml backend/run_dev.py
git add backend/Dockerfile backend/.dockerignore backend/SETUP.md
git add frontend/src/data/curriculumCatalog.json
git add storage/knowledge-sources/manifest.json
git add storage/knowledge-sources/ai-ml storage/knowledge-sources/algorithms
git add storage/knowledge-sources/cs-foundations storage/knowledge-sources/data-system
git add storage/knowledge-sources/llm-agents storage/knowledge-sources/supplement
git add storage/knowledge-sources/web-engineering
git add deploy/inference/lora_weights_final
git add backend/storage/models/models--BAAI--bge-small-zh-v1.5 screenshots

git status
git commit -m "docs: 整理 GitHub 上传范围与项目复刻指南"
git push origin test
```

推送前请检查 `git status`，确认没有出现 `.env`、`backend/.env`、`node_modules`、`frontend/dist` 等敏感或构建目录；模型权重目录应只包含 `models--BAAI--bge-small-zh-v1.5`。

## 6. 其他开发者复刻步骤

### 6.1 环境要求

- Python 3.12
- Node.js 20+，并启用 Corepack
- pnpm 11.9.0（由项目 `packageManager` 固定）
- Docker 与 Docker Compose，或本机 PostgreSQL（需安装 pgvector 扩展）
- 可选：Valkey/Redis；未配置时资源生成会退回数据库兜底模式

### 6.2 克隆与配置环境变量

```bash
git clone https://github.com/datuyio/zhike-ai-learning-workbench.git
cd zhike-ai-learning-workbench

cp .env.example .env
```

编辑 `.env`：

- 配置 `JWT_SECRET_KEY` 和 `ENCRYPTION_KEY`，长度至少 32 位。
- 本地知识库使用 `RAG_BACKEND=local_pgvector`。
- `LOCAL_EMBEDDING_CACHE_DIR` 默认指向 `backend/storage/models`，模型权重已随仓库提供，新环境通常无需联网下载。
- 数据库、Redis 地址按本机环境调整。
- 对话模型 API Key 为可选；未配置时本地知识库检索、课程同步和学习路径仍可用。

### 6.3 启动基础设施并初始化数据库

Docker 方式：

```bash
docker compose up -d postgres valkey
```

本机 PostgreSQL 方式：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

初始化数据库：

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
```

macOS/Linux 对应使用：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

### 6.4 同步课程体系并导入本地知识库

```bash
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\seed_curriculum_catalog.py
.\.venv\Scripts\python.exe scripts\import_knowledge_corpus.py
.\.venv\Scripts\python.exe scripts\sync_local_documents_to_concepts.py --rebuild-paths
```

说明：

- `import_knowledge_corpus.py` 从 `storage/knowledge-sources/manifest.json` 读取语料清单。
- 模型权重随仓库放在 `backend/storage/models/models--BAAI--bge-small-zh-v1.5`，导入时优先使用该缓存，不强制联网下载；若缓存不完整，仍会尝试从 Hugging Face 补全。
- 默认跳过 `NOASSERTION` 和未声明许可证的内容。
- 同步脚本会把 Markdown 映射为知识点、章节、先修关系和切片关联，并重建管理员学习路径。

### 6.5 启动后端、前端和沙箱

后端：

```bash
cd backend
python run_dev.py
```

前端：

```bash
cd frontend
corepack enable
corepack prepare pnpm@11.9.0 --activate
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

代码沙箱（可选，在线代码执行需要）：

```bash
cd backend/sandbox-service
npm install
npm start
```

启动后：

- 前端：`http://localhost:5173`
- 后端 API：`http://localhost:8001`
- API 文档：`http://localhost:8001/docs`
- 沙箱健康检查：`http://127.0.0.1:8003/health`

也可以直接运行根目录的 `scripts/start-dev.ps1` 或 `start-dev.bat`。

### 6.6 验证复刻成功

```bash
# 后端测试
cd backend && python -m pytest

# 前端测试与构建
cd frontend && corepack pnpm test
cd frontend && corepack pnpm build
```

浏览器验证：

1. 访问 `http://localhost:8001/docs`，应显示 FastAPI 文档。
2. 使用管理员账号登录。
3. 访问 `/learning-path`，应看到由本地语料生成的课程知识点。
4. 在知识库页搜索“高可用系统”，应返回本地 Markdown 引用。
5. `GET /api/v1/courses/with-knowledge` 应返回 7 门已就绪课程。

## 7. 常见问题

| 问题 | 处理 |
|---|---|
| 导入时找不到 `storage/knowledge-sources/manifest.json` | 确认知识库语料目录已随仓库拉取，未按旧 `.gitignore` 被过滤 |
| 导入时提示课程未同步 | 先运行 `seed_curriculum_catalog.py` |
| 模型加载失败 | 确认 `backend/storage/models/models--BAAI--bge-small-zh-v1.5` 已随仓库拉取；缓存不完整时可设置 `HF_ENDPOINT=https://hf-mirror.com` 或手动补全 |
| Docker 容器找不到仓库模型 | 把模型目录复制到根 `storage/models/models--BAAI--bge-small-zh-v1.5`，Docker 默认挂载的 `/app/storage/models` 即可命中；或调整 `LOCAL_EMBEDDING_CACHE_DIR` 指向实际挂载路径 |
| `CREATE EXTENSION vector` 失败 | 使用带 pgvector 的 PostgreSQL 镜像，或本机安装 pgvector 扩展 |
| 前端依赖结构异常 | 删除 `frontend/node_modules`，按 `pnpm-lock.yaml` 重新安装 |
| 学习路径节点少 | 重新运行 `sync_local_documents_to_concepts.py --rebuild-paths` |
| 页面能跑但聊天无 AI 回复 | 对话功能需要配置至少一个模型供应商 API Key；本地知识库检索不依赖该 Key |