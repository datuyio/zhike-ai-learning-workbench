# 计算机与人工智能课程体系规划与 GitHub 学习资料目录

> 快照日期：2026-08-17  
> 配套数据文件：`frontend/src/data/curriculumCatalog.json`  
> 定位：为智课平台规划一套「学、练、测、评、沉淀」闭环的计算机科学与人工智能课程体系，并提供可直接接入网站的资料目录。

---

## 1. 体系设计目标

本课程体系面向智课的计算机与人工智能学科定位，设计目标如下：

1. **覆盖完整成长路径**：从零基础到可独立完成真实项目和论文复现，而不是零散资料堆砌。
2. **形成闭环**：每门主线课程都配套讲义、代码实验、测评题、项目与拓展阅读，可接入智课现有学习路径、资源大厅、练习评估和学情画像。
3. **可落地到智课模型**：资料按课程、章节、知识点、资源四级映射，与 `courses`、`course_sections`、`course_concepts`、`resources` 数据模型一一对应。
4. **重视合规与维护性**：优先选择许可证清晰、社区活跃、持续更新的开源资料，外部资料以链接和引用方式接入，避免直接搬运版权内容。

---

## 2. 课程体系总览

| 主线 | 定位 | 阶段覆盖 | 核心目标 |
|---|---|---|---|
| 计算机科学基础 | 所有方向共同底座 | L0-L2 | 编程入门、CS 核心、系统与工程实践 |
| 算法与数据结构 | 编程硬实力 | L1-L3 | 算法基础、竞赛进阶、面试冲刺 |
| Web 与前端工程 | 网站与应用开发 | L1-L2 | HTML/CSS/JS、前端框架与现代工程化 |
| 数据与系统设计 | 生产级工程能力 | L2 | 系统设计、数据工程、MLOps |
| 机器学习与深度学习 | AI 理论与实现 | L1-L3 | ML 入门、算法手写、深度学习与论文复现 |
| 大模型与 AI Agent | 生成式 AI 前沿 | L2-L4 | 提示工程、RAG、Agent、大模型训练 |
| 综合自修与学术素养 | 贯穿全阶段 | L0-L4 | 职业路线、项目驱动、论文阅读、视频课程 |

### 阶段定义

| 阶段 | 名称 | 能力目标 | 对应智课难度 |
|---|---|---|---|
| L0 | 入门启蒙 | 能读懂代码、完成小练习，建立计算思维 | basic |
| L1 | 基础 | 掌握一门语言和 CS 核心知识，能完成课程作业 | basic / medium |
| L2 | 进阶 | 掌握算法、Web、数据或 ML 主线，能完成专题项目 | medium |
| L3 | 高级 | 能进行系统设计、深度学习/LLM 实践、竞赛或面试冲刺 | advanced |
| L4 | 实战/研究 | 能独立完成真实项目、论文复现或大模型训练实验 | advanced |

---

## 3. 详细资料目录

星标数为快照数据，仅用于判断社区热度；实际接入前建议再次核验仓库状态与许可证。

### 3.1 计算机科学基础

#### L0 入门启蒙（约 4 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| free-programming-books | [EbookFoundation/free-programming-books](https://github.com/EbookFoundation/free-programming-books) | CC-BY-4.0 | 39.5 万 | 阅读 | 资源大厅、知识库 | 作为拓展阅读包外链库，按主题筛选章节 |
| Python-100-Days | [jackfrued/Python-100-Days](https://github.com/jackfrued/Python-100-Days) | NOASSERTION | 18.5 万 | 课程 | 学习路径、资源大厅、代码实验 | 拆分为 Python 基础课程章节 |
| Python-programming-exercises | [zhiwehu/Python-programming-exercises](https://github.com/zhiwehu/Python-programming-exercises) | NOASSERTION | 3.0 万 | 题库 | 练习评估、资源大厅 | 筛选题目进入阶段测评 |

#### L1 计算机科学核心（约 20 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| OSSU Computer Science | [ossu/computer-science](https://github.com/ossu/computer-science) | MIT | 20.8 万 | 课程体系 | 学习路径、课程建设台 | 作为课程体系骨架 |
| CS 自学指南 | [PKUFlyingPig/cs-self-learning](https://github.com/PKUFlyingPig/cs-self-learning) | MIT | 7.5 万 | 课程体系 | 学习路径、知识库 | 作为中文主路线图 |
| TeachYourselfCS-CN | [izackwu/TeachYourselfCS-CN](https://github.com/izackwu/TeachYourselfCS-CN) | CC-BY-SA-4.0 | 2.2 万 | 阅读 | 知识库、资源大厅 | 整理为经典书单 |
| The Missing Semester 中文版 | [missing-semester-cn/missing-semester-cn](https://github.com/missing-semester-cn/missing-semester-cn) | NOASSERTION | 0.7 万 | 讲义 | 知识库、学习路径 | 作为工程工具入门章节 |
| Every Programmer Should Know | [mtdvio/every-programmer-should-know](https://github.com/mtdvio/every-programmer-should-know) | CC-BY-4.0 | 10.0 万 | 参考 | 知识库、资源大厅 | 生成速查问答卡片 |

#### L2 系统与工程实践（约 12 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| Build Your Own X | [codecrafters-io/build-your-own-x](https://github.com/codecrafters-io/build-your-own-x) | 未声明 | 54.0 万 | 项目 | 资源大厅、代码实验 | 精选 8-12 个项目作为实战项目库 |
| Public APIs | [public-apis/public-apis](https://github.com/public-apis/public-apis) | MIT | 46.3 万 | 参考 | 资源大厅、代码实验 | 为项目实训提供数据源 |

### 3.2 算法与数据结构

#### L1 算法基础（约 10 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| The Algorithms Python | [TheAlgorithms/Python](https://github.com/TheAlgorithms/Python) | MIT | 22.4 万 | 参考 | 知识库、代码实验 | 作为算法代码示例 |
| The Algorithms Java | [TheAlgorithms/Java](https://github.com/TheAlgorithms/Java) | MIT | 6.6 万 | 参考 | 知识库、代码实验 | 与 Python 版形成多语言对照 |

#### L2 算法进阶（约 12 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| labuladong 算法 | [labuladong/fucking-algorithm](https://github.com/labuladong/fucking-algorithm) | 未声明 | 13.5 万 | 讲义 | 学习路径、知识库 | 按专题整理为进阶讲义 |
| OI Wiki | [OI-wiki/OI-wiki](https://github.com/OI-wiki/OI-wiki) | 未声明 | 2.7 万 | 参考 | 知识库、学习路径 | 作为竞赛进阶章节资料 |

#### L3 面试与竞赛冲刺（约 8 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| LeetCode Solutions | [kamyu104/LeetCode-Solutions](https://github.com/kamyu104/LeetCode-Solutions) | MIT | 0.6 万 | 题库 | 练习评估、资源大厅 | 按专题生成测评与补救卡 |
| Coding Interview University | [jwasham/coding-interview-university](https://github.com/jwasham/coding-interview-university) | CC-BY-SA-4.0 | 35.9 万 | 课程 | 学习路径、课程建设台 | 作为面试冲刺课程模板 |
| CS-Notes | [CyC2018/CS-Notes](https://github.com/CyC2018/CS-Notes) | 未声明 | 18.5 万 | 参考 | 知识库、练习评估 | 整理面试知识点库 |

### 3.3 Web 与前端工程

#### L1 Web 基础（约 12 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| The Odin Project Curriculum | [TheOdinProject/curriculum](https://github.com/TheOdinProject/curriculum) | NOASSERTION | 1.3 万 | 课程 | 学习路径、课程建设台 | 作为 Web 开发主线课程 |
| 50 Projects 50 Days | [bradtraversy/50projects50days](https://github.com/bradtraversy/50projects50days) | MIT | 4.1 万 | 代码实验 | 资源大厅、代码实验 | 按难度绑定前端课程节点 |

#### L2 JavaScript 深入（约 8 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| You Don't Know JS | [getify/You-Dont-Know-JS](https://github.com/getify/You-Dont-Know-JS) | NOASSERTION | 18.5 万 | 阅读 | 知识库、资源大厅 | 生成 JS 深入阅读包 |
| JavaScript Questions | [lydiahallie/javascript-questions](https://github.com/lydiahallie/javascript-questions) | MIT | 6.5 万 | 题库 | 练习评估、知识库 | 作为 JS 测评题库 |

### 3.4 数据与系统设计

#### L2 系统设计与数据工程（约 12 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| System Design Primer | [donnemartin/system-design-primer](https://github.com/donnemartin/system-design-primer) | NOASSERTION | 36.4 万 | 课程 | 学习路径、知识库、练习评估 | 面试题进入测评题库 |
| Data Engineering Zoomcamp | [DataTalksClub/data-engineering-zoomcamp](https://github.com/DataTalksClub/data-engineering-zoomcamp) | 未声明 | 4.5 万 | 课程 | 学习路径、资源大厅 | 周任务转成项目实训 |
| MLOps Zoomcamp | [DataTalksClub/mlops-zoomcamp](https://github.com/DataTalksClub/mlops-zoomcamp) | 未声明 | 1.5 万 | 课程 | 学习路径、资源大厅 | 作为 AI 工程化课程 |

### 3.5 机器学习与深度学习

#### L1 AI/ML 入门（约 12 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| ML For Beginners | [microsoft/ML-For-Beginners](https://github.com/microsoft/ML-For-Beginners) | MIT | 8.9 万 | 课程 | 学习路径、知识库、练习评估 | 测验直接进入阶段测评 |
| AI For Beginners | [microsoft/AI-For-Beginners](https://github.com/microsoft/AI-For-Beginners) | MIT | 6.5 万 | 课程 | 学习路径、知识库 | 作为 AI 通识主线 |
| Data Science For Beginners | [microsoft/Data-Science-For-Beginners](https://github.com/microsoft/Data-Science-For-Beginners) | MIT | 3.7 万 | 课程 | 学习路径、知识库 | 作为数据科学入门课程 |

#### L2 机器学习深入（约 10 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| Homemade Machine Learning | [trekhleb/homemade-machine-learning](https://github.com/trekhleb/homemade-machine-learning) | MIT | 2.5 万 | 代码实验 | 代码实验、学习路径 | 手写算法原理实验 |
| ML Specialization Notes | [greyhatguy007/Machine-Learning-Specialization-Coursera](https://github.com/greyhatguy007/Machine-Learning-Specialization-Coursera) | MIT | 0.8 万 | 讲义 | 知识库、资源大厅 | 整理为 ML 章节讲义 |

#### L3 深度学习（约 16 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| 李宏毅深度学习笔记 | [unclestrong/DeepLearning_LHY21_Notes](https://github.com/unclestrong/DeepLearning_LHY21_Notes) | MIT | 0.2 万 | 讲义 | 知识库、学习路径 | 作为深度学习中文讲义 |
| Fastbook | [fastai/fastbook](https://github.com/fastai/fastbook) | NOASSERTION | 2.5 万 | 课程 | 学习路径、代码实验 | Notebook 转代码实验 |
| Neural Networks Zero to Hero | [karpathy/nn-zero-to-hero](https://github.com/karpathy/nn-zero-to-hero) | MIT | 2.4 万 | 课程 | 学习路径、代码实验 | 从零手写网络课程 |
| Micrograd | [karpathy/micrograd](https://github.com/karpathy/micrograd) | MIT | 1.7 万 | 代码实验 | 代码实验、知识库 | 反向传播核心实验 |
| Annotated Deep Learning Papers | [labmlai/annotated_deep_learning_paper_implementations](https://github.com/labmlai/annotated_deep_learning_paper_implementations) | MIT | 6.7 万 | 参考 | 知识库、资源大厅 | 论文复现资料库 |

### 3.6 大模型与 AI Agent

#### L2 提示工程与生成式 AI（约 8 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| Generative AI For Beginners | [microsoft/Generative-AI-For-Beginners](https://github.com/microsoft/Generative-AI-For-Beginners) | MIT | 11.8 万 | 课程 | 学习路径、知识库、练习评估 | 与智课 Agent 架构高度契合 |
| Prompt Engineering Guide | [dair-ai/Prompt-Engineering-Guide](https://github.com/dair-ai/Prompt-Engineering-Guide) | MIT | 7.8 万 | 参考 | 知识库、资源大厅 | 提示工程技术手册 |
| LLM Cookbook 中文版 | [datawhalechina/llm-cookbook](https://github.com/datawhalechina/llm-cookbook) | 未声明 | 2.5 万 | 课程 | 学习路径、知识库 | 中文 LLM 课程 |

#### L3 LLM 深入与 Agent 开发（约 12 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| LLM Course | [mlabonne/llm-course](https://github.com/mlabonne/llm-course) | Apache-2.0 | 8.2 万 | 课程 | 学习路径、知识库 | LLM 进阶主线 |
| Hugging Face Agents Course | [huggingface/agents-course](https://github.com/huggingface/agents-course) | Apache-2.0 | 3.1 万 | 课程 | 学习路径、代码实验 | Agent 开发主线 |
| OpenAI Cookbook | [openai/openai-cookbook](https://github.com/openai/openai-cookbook) | MIT | 7.5 万 | 参考 | 知识库、代码实验 | API 开发手册 |
| Anthropic Courses | [anthropics/courses](https://github.com/anthropics/courses) | NOASSERTION | 2.3 万 | 课程 | 学习路径、知识库 | Agent 工作流课程 |

#### L4 大模型训练与复现（约 12 周）

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| nanoGPT | [karpathy/nanoGPT](https://github.com/karpathy/nanoGPT) | MIT | 6.2 万 | 项目 | 代码实验、资源大厅 | 大模型训练实战项目 |
| llm.c | [karpathy/llm.c](https://github.com/karpathy/llm.c) | MIT | 3.1 万 | 项目 | 代码实验、资源大厅 | 系统级大模型实验 |

### 3.7 综合自修与学术素养

#### 贯穿全阶段补给

| 资料 | GitHub 仓库 | 许可证 | 星标 | 类型 | 智课模块 | 使用建议 |
|---|---|---|---|---|---|---|
| Developer Roadmap | [kamranahmedse/developer-roadmap](https://github.com/kamranahmedse/developer-roadmap) | NOASSERTION | 36.5 万 | 参考 | 学习路径、知识库 | 职业方向地图 |
| Project Based Learning | [practical-tutorials/project-based-learning](https://github.com/practical-tutorials/project-based-learning) | MIT | 28.0 万 | 项目 | 资源大厅、代码实验 | 项目实训库 |
| Papers We Love | [papers-we-love/papers-we-love](https://github.com/papers-we-love/papers-we-love) | 未声明 | 10.9 万 | 阅读 | 知识库、资源大厅 | 论文研读资料库 |
| ML YouTube Courses | [dair-ai/ML-YouTube-Courses](https://github.com/dair-ai/ML-YouTube-Courses) | CC0-1.0 | 1.7 万 | 参考 | 资源大厅、学习路径 | 视频课程推荐入口 |

---

## 4. 智课闭环映射

| 闭环环节 | 智课模块 | 资料与课程落地方式 |
|---|---|---|
| 学 | 课程建设台、知识大本营、AI 对话、课程资料问答 | 用主线课程建课程与章节，将讲义、书单接入知识库 |
| 练 | 代码实验、项目资源、代码沙箱 | 将 code_lab / 项目资料绑定到知识点，提供可运行实验 |
| 测 | 练习评估、阶段测评题 | 将题库和测验导入测评，自动评分与归因 |
| 评 | 学情画像、错题补救卡 | 掌握度与薄弱点回写画像，生成个性化补救建议 |
| 沉淀 | 资源大厅、资源审核、拓展阅读 | 生成资源进入大厅，社区审核后复用 |

---

## 5. 智课承载方式与落地步骤

1. **课程建设台建课程**：按 7 条主线创建课程，例如「机器学习」「深度学习」「大模型与 Agent」。
2. **导入章节与知识点**：按阶段将 GitHub 课程拆成章节，并配置前置依赖与难度。
3. **知识大本营接入资料**：将许可证允许的 Markdown/Notebook 内容转成 PDF 或 Markdown 上传，外链资料作为引用源。
4. **资源大厅沉淀**：将代码实验、项目、题库、阅读包创建为资源，绑定课程与知识点。
5. **练习评估建题**：从题库筛选阶段测评题，配置 Rubric 或客观题答案。
6. **学习路径发布**：让系统按知识点依赖生成个性化路径，供学生逐步学习。
7. **画像与补救闭环**：根据测评结果更新掌握度，为薄弱点生成补救卡。

---

## 6. 许可证与合规注意事项

1. 目录中标注「未声明」的仓库未提供明确开源许可证，接入前必须联系作者确认使用范围，仅允许作为外链引用。
2. `CC-BY-4.0`、`CC-BY-SA-4.0`、`CC0-1.0` 资料可引用或再分发，但需保留署名或遵守相同方式共享要求。
3. `MIT`、`Apache-2.0` 资料适合复制到课程知识库，仍需保留原版权声明。
4. 正式页面展示外部资料时，应优先使用外链，避免在网站内重新托管大体积仓库。
5. 星标与仓库状态会变化，接入前应重新核验，并在后台记录资料版本与来源。

---

## 7. 配套数据文件

`frontend/src/data/curriculumCatalog.json` 是配套的结构化目录，结构如下：

```json
{
  "schemaVersion": "1.0",
  "updatedAt": "2026-08-17",
  "scope": "计算机科学与人工智能",
  "tracks": [
    {
      "id": "cs-foundations",
      "title": "计算机科学基础",
      "stages": [
        {
          "stage": "L0",
          "title": "入门启蒙",
          "resources": []
        }
      ]
    }
  ],
  "closedLoop": {}
}
```

前端可读取该文件生成「课程体系」或「资料目录」页面；管理端可按主线、阶段和资源类型批量导入课程与资源。

---

## 8. 课程数据同步脚本

仓库提供 `backend/scripts/seed_curriculum_catalog.py`，用于把课程体系目录同步为智课中的已发布课程：

```bash
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\seed_curriculum_catalog.py
```

脚本按稳定 `slug` 与 `code` 幂等同步：

- 每条主线创建或更新一门已发布课程；
- 每个阶段创建或更新一个课程章节；
- 每项开源资料创建或更新一个已发布知识点；
- 重复执行不会产生重复课程、章节或知识点。

同步完成后，可在课程切换器中自由选择任意课程，并进入学习路径查看对应阶段与知识点。

---

## 9. 已落地的课程与本地知识库

课程同步脚本与 Markdown 批量导入脚本已完成首轮执行，当前本地 `local_pgvector` 知识库统计如下：

| 课程主线 | 本地文档 | 可检索切片 |
|---|---:|---:|
| 计算机科学基础 | 125 | 696 |
| 算法与数据结构 | 67 | 3766 |
| Web 与前端工程 | 24 | 5329 |
| 数据与系统设计 | 120 | 2167 |
| 机器学习 | 387 | 7373 |
| 大模型与 AI Agent | 438 | 4722 |
| 综合自修与学术素养 | 4 | 114 |

执行顺序：

```bash
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\seed_curriculum_catalog.py
.\.venv\Scripts\python.exe scripts\import_knowledge_corpus.py
```

默认只导入许可证明确的开源语料；`NOASSERTION` 仓库保留为外链引用。`system-design-primer` 因未声明许可证未托管，数据与系统设计课程改用 MIT 授权的 `study8677/awesome-architecture`。

## 10. 后续迭代建议

1. 每季度重新核验仓库状态、许可证与维护活跃度。
2. 为每门课程补充自有讲义，GitHub 资料仅作为基础素材。
3. 增加学科竞赛、就业方向与科研方向的分流路线。
4. 将资料目录接入管理端课程建设台，支持一键导入课程骨架。
5. 对测验、代码实验建立质量评估标准，纳入资源审核流程。
