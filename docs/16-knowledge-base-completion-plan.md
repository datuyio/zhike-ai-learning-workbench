# 本地知识库补全实施记录

> 更新日期：2026-08-18  
> 目标：把计算机与人工智能课程体系的开放语料导入本地知识库，打通「Markdown 解析 → 分块 → BGE 向量化 → PGVector 入库 → 混合检索 → 引用问答」链路。

## 1. 完成结果

| 项 | 结果 |
|---|---|
| 运行模式 | `RAG_BACKEND=local_pgvector` |
| 数据库 | PostgreSQL `zhike_workshop`，pgvector 扩展可用 |
| 已同步课程主线 | 7 条：计算机科学基础、算法与数据结构、Web 与前端工程、数据与系统设计、机器学习、大模型与 AI Agent、综合自修 |
| 本地文档 | 1165 份 |
| 可检索向量切片 | 24167 个 |
| 许可证策略 | 只导入 `MIT`、`Apache-2.0`、`CC-BY-4.0`、`CC-BY-SA-4.0`、`CC0-1.0`；`NOASSERTION` 内容不批量入库 |
| 检索方式 | BM25 + PGVector 余弦相似度加权融合 |
| 前端可用课程 | `GET /api/v1/courses/with-knowledge` 返回 7 门已就绪课程 |

课程级统计：

| 课程 slug | 文档 | 切片 |
|---|---:|---:|
| `cs_foundations` | 125 | 696 |
| `algorithms` | 67 | 3766 |
| `web_engineering` | 24 | 5329 |
| `data_system` | 120 | 2167 |
| `ai_ml` | 387 | 7373 |
| `llm_agents` | 438 | 4722 |
| `supplement` | 4 | 114 |

## 2. 实施链路

### 2.1 语料清单

抓取结果写入 `storage/knowledge-sources/manifest.json`，保留课程主线、仓库、许可证、文件路径、SHA-256 和字节数。资料目录仍以 [15-computer-ai-curriculum.md](./15-computer-ai-curriculum.md) 和 `frontend/src/data/curriculumCatalog.json` 为课程体系依据。

原始 `system-design-primer` 许可证为 `NOASSERTION`，按项目合规规则不作为托管语料；数据与系统设计改用 MIT 授权的 `study8677/awesome-architecture`，导入 120 份 Markdown 文档、2167 个切片。

### 2.2 课程同步

```bash
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\seed_curriculum_catalog.py
```

脚本按稳定 slug 与 code 幂等同步课程、阶段章节、资料知识点和先修关系。新知识点会先 `flush()` 获得主键，再建立 `ConceptPrerequisite`，避免空 `concept_id`。

### 2.3 批量导入

```bash
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\import_knowledge_corpus.py
```

导入脚本读取 manifest，逐个解析 Markdown、生成 Embedding、写入本地文档与切片，并按内容哈希去重。默认跳过未声明许可证文件；支持 `--tracks`、`--repos`、`--limit`、`--offset` 和 `--dry-run` 做分批或验证。

本地解析能力：

- 支持 PDF、Markdown、MDX 和纯文本。
- Markdown 保留多级标题路径、章节编号和正文章节定位。
- 长标题按数据库列宽截断，JSON 中仍保留完整标题路径。
- YAML frontmatter、图片链接和导航占位不会进入可检索正文。
- 扫描版 PDF 仍需 OCR；数据库向量维度与 Embedding 模型必须一致。

### 2.4 本地语料到学习路径知识点映射

Markdown 入库后，文档本身只进入检索链路；学习路径仍需由 `CourseConcept` 驱动。运行：

```bash
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\sync_local_documents_to_concepts.py --rebuild-paths
```

同步脚本按以下来源提取稳定学习主题：

- Markdown 相对路径与仓库目录结构；
- `DocumentChunk.heading_path_json` 中的多级标题；
- 原始 README 与中文原始文件优先，翻译文件不重复生成主题；
- 无独立主题的维护文件、元信息和翻译切片归入仓库总览知识点。

脚本会创建或更新 `CourseConcept`、`CourseSection`、`ConceptPrerequisite`，把切片写入 `DocumentChunk.concept_id`，并重建管理员学习路径。编码使用稳定哈希，可重复执行；重复运行不会新增重复知识点或重复变更切片关联。旧知识点被归档时，会同步移除其旧先修边。

本地主题映射结果：

| 课程 slug | 本地候选主题 | 已发布知识点 | 已关联切片 |
|---|---:|---:|---:|
| `ai_ml` | 70 | 80 | 7373 |
| `algorithms` | 38 | 45 | 3766 |
| `cs_foundations` | 55 | 65 | 696 |
| `data_system` | 43 | 47 | 2167 |
| `llm_agents` | 84 | 93 | 4722 |
| `supplement` | 0 | 4 | 114 |
| `web_engineering` | 80 | 84 | 5329 |

## 3. 后端修复

1. `seed_curriculum_catalog.py` 新增知识点后调用 `db.flush()`，修复先修关系 `concept_id` 为空的问题。
2. `KnowledgeRepository.get_courses_with_knowledge()` 返回课程 UUID；管理员可查看全部就绪课程，学生按有效 `CourseMembership` 过滤。
3. 延迟导入 `iflytek.status_labels` 与 `ingestion_status_builder` 的 iflytek 依赖，解决本地后端加载时的循环导入。
4. 文档序列化同时读取 `chatdoc_chunk_total` 与 `local_chunk_total`。
5. `courses/{course_id}/ai-context` 在 `local_pgvector` 模式返回本地就绪状态、文档数、QA 模式和阻断原因。
6. `sync_local_documents_to_concepts.py` 只读取已发布知识点作为仓库总览依据；同步时清理不再匹配当前映射的先修边，归档旧知识点时同时移除其旧边，避免已归档概念继续阻塞新学习路径节点。

## 4. 前端修复

1. `coursesWithKnowledge` 改为调用用户侧 `GET /api/v1/courses/with-knowledge`。
2. 学习路径解析不再为后端未返回的 `mastery_score` 伪造默认值。
3. Vitest 排除 Playwright e2e 目录，避免 `pnpm test` 误收集。
4. 恢复前端治理规则：统一 JSON 解析、统一浏览器存储、中文注释和导出函数返回类型。

## 5. 验证结果

| 检查 | 结果 |
|---|---|
| 后端全量测试 | `119 passed` |
| 后端 Ruff | 通过 |
| 前端全量 Vitest | `61` 个文件、`261` 个用例通过 |
| 前端 TypeScript | 通过 |
| 前端生产构建 | 通过 |
| 用户侧课程 API | `/api/v1/courses/with-knowledge` 返回 7 门就绪课程 |
| 本地检索 | `data_system` 查询“高可用系统”可返回本地引用 |
| 学习路径节点 | `data_system=47`、`web_engineering=84`，其余课程同步提升到 45 至 93 个节点 |
| 知识点与切片关联 | 7 门课程共 418 个已发布知识点，24167 个切片全部关联 `concept_id` |
| 同步幂等性 | 连续实跑后 `changed_chunks=0`，无重复知识点、无已归档知识点参与先修边 |

## 6. 剩余边界

- 外部对话模型仍需配置可用的 API Key 或代理，本地向量检索不依赖这些凭据。
- 管理端逐文件上传、资源生成和 AI 对话的完整线上联调，仍受当前外部模型凭据与网络环境限制。
- 正式部署前应把供应商密钥和数据库凭据迁移到生产环境变量，不随仓库或演示截图分发；本地 Embedding 模型权重按项目要求随仓库提供，部署时需同步检查 `backend/storage/models/models--BAAI--bge-small-zh-v1.5` 的完整性与许可证。
