# 后端启动注意事项

> 给所有要在自己电脑上跑后端的同学（联调、开发、评审）看。
> 先看这份，再启动，能省掉 90% 的环境报错。

---

## 0. 一句话总览

后端依赖三样东西：**Python 环境 + PostgreSQL（带 pgvector 扩展）+ Valkey/Redis**。
三样齐了才能跑。下面分两种启动方式，选一种即可。

---

## 1. 方式 A：Docker 一键启动（推荐联调用）

```bash
# 在仓库根目录执行
docker compose up --build
```

⚠️ **必须带 `--build`**。原因见下方「常见报错」第 1 条。

- 后端跑在 `http://localhost:8001`
- 数据库用 `pgvector/pgvector:pg16` 镜像，自带 pgvector 扩展，无需手动装
- 首次启动会自动跑 `alembic upgrade head` 建表

---

## 2. 方式 B：本地 venv 启动

适合改代码、调试。

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate              # Windows
# source .venv/bin/activate          # macOS / Linux
pip install -r requirements.txt
```

还需要单独准备数据库和缓存（见第 3、4 节），然后：

```bash
alembic upgrade head
python run_dev.py
```

---

## 3. 数据库：必须装 pgvector 扩展

后端用 pgvector 存向量，所以 Postgres 里必须有 `vector` 扩展。

| 情况 | 要不要手动装扩展 |
|---|---|
| 用 Docker 的 `pgvector/pgvector:pg16` 镜像 | ❌ 不用，镜像自带 |
| 用自己本机的 Postgres | ✅ 要手动装，见下 |

**本机 Postgres 装扩展步骤**（仅本机启动需要）：

1. 确认 Postgres 版本 ≥ 13
2. 装扩展（Windows 可用 EnterpriseDB 的 StackBuilder，或编译安装）
3. 连进数据库执行：
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```
   （这两行 `backend/db/init.sql` 里也有，Docker 启动会自动跑。）

---

## 4. 缓存：Valkey 或 Redis

默认连 `redis://localhost:6379/0`。Docker 会自动起一个 Valkey；本地启动的话自己装一个 Redis 或 Valkey 跑着就行。

---

## 5. 常见报错对照表

| 报错 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'pgvector'`（Docker 里） | Docker 镜像是旧的，在 pgvector 加入依赖之前构建的 | `docker compose up --build`，**必须带 --build 重建镜像** |
| `ModuleNotFoundError: No module named 'jieba'` 或 `'rank_bm25'` | 历史遗留：这俩包以前没写进 requirements.txt | 拉最新代码后 `pip install -r requirements.txt` 即可（已补） |
| `ModuleNotFoundError: No module named 'pgvector'`（本地 venv 里） | venv 没装全依赖 | 同上，`pip install -r requirements.txt` |
| `CREATE EXTENSION vector` 报错 / 连接数据库失败 | 本机 Postgres 没装 pgvector 扩展，或连接信息不对 | 见第 3 节；检查 `.env` 里的 `DATABASE_URL` |
| `alembic upgrade head` 报版本冲突 | 迁移历史有改动 | 先 `alembic current` 看当前版本，再对症处理；别盲目 downgrade |

---

## 6. 环境变量

复制 `.env.example`（或向项目维护者要 `.env`），放在仓库根目录。关键字段：

```
DATABASE_URL=postgresql+psycopg://zhike:zhike_password@localhost:5432/zhike_workshop
VALKEY_URL=redis://localhost:6379/0
```

Docker 模式下 `docker-compose.yml` 会把 host 改成容器名（`postgres` / `valkey`），不用管。

---

## 7. 代码沙箱微服务（联调"代码执行"功能时需要）

AI 自习室的代码执行走 Node + Pyodide 微服务，不跟后端一起起，**只有联调/演示代码执行功能时才需要单独启动**。

```bash
cd backend/sandbox-service
npm install         # 装 pyodide + express，首次较慢（Pyodide 体积大）
npm start           # 启动沙箱微服务，默认监听 http://127.0.0.1:8003
```

- 后端通过 `.env` 里的 `SANDBOX_SERVICE_URL=http://127.0.0.1:8003` 调用它，起不来时代码执行接口会返回 503。
- 起来后访问 `http://127.0.0.1:8003/health`，返回 `{"status":"ready"}` = 成功（首次启动需加载 Pyodide，可能等几秒到 ready）。
- **本机可选优化**：若不想把 Pyodide（数百 MB）装进项目目录，可在 `.env` 里设 `SANDBOX_NODE_MODULES=D:/zhike-sandbox-deps/node_modules` 指向自备依赖目录，仅本机生效，不影响别人拉代码后正常 `npm install`。

---

## 8. 验证启动成功

后端起来后访问 `http://localhost:8001/docs`，能看到 FastAPI 自动文档页 = 成功。

---

## 9. LoRA 推理服务部署（T-B-11，需要 GPU）

本地微调好的 Qwen2.5-7B 推理服务，代码和权重都在仓库 `deploy/inference/` 目录。
它跑在 **WSL2 / Linux** 里（`.venv` 的 Windows Python 跑不了 torch 推理）；Windows 端只做「注册」这一步。

> **只有需要本机跑 LoRA 推理服务的人才要做这节**（如联调微调效果的场景）。
> 只把项目拉下来跑后端的话，本节能跳过。

### 9.0 需要准备的材料

以下材料**不放仓库**，拉取到新电脑后需自行准备：

**① 基座模型（必装，约 15GB）**：`Qwen/Qwen2.5-7B-Instruct`
LoRA 权重是增量，必须配对基座模型。下载到 `MODELS_ROOT`（默认 `/root/models`）：

```bash
# Hugging Face
huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir /root/models/Qwen2.5-7B-Instruct
# 国内用 ModelScope
# python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen2.5-7B-Instruct', cache_dir='/root/models')"
```

**② LoRA 微调权重（已入库，无需准备）**：在仓库 `deploy/inference/lora_weights_final/`（~88MB），随代码一起拉取。

**③ 训练数据（仅重新训练时需要）**：7053 条 QA 对（`qa_data_all.jsonl`，Alpaca 格式）不在仓库。
如要重新微调，需先用 5 本教材生成数据（生成脚本在 `E:\testing\TB10\`，仅本机，不提交）：

| 教材 PDF | 作者 |
|---|---|
| 《机器学习》 | 周志华 |
| 《统计学习方法》 | 李航 |
| 《深度学习》（花书） | Ian Goodfellow 等 |
| Deep Learning Notes | — |
| Pattern Recognition and Machine Learning (PRML) | Christopher M. Bishop |

生成流程：PDF 文本提取 → 智能切块 → 大模型生成 QA 对 → 合并去重 → `qa_data_all.jsonl`，然后放到 `deploy/inference/` 目录并设 `TRAIN_DATA_PATH`。

> 也可以直接向 B 同学要训练好的数据或脚本，不需要重复生成。

### 9.2 推理服务（WSL2 内）

前置条件：NVIDIA GPU + CUDA 12.x、Python 3.10+、约 8GB 显存（4-bit 量化）。

```bash
# 进入推理服务目录
cd deploy/inference

# 1. 建虚拟环境装依赖（按自己 CUDA 版本选 torch 安装命令，见 https://pytorch.org）
python3.11 -m venv /root/venvs/inference
/root/venvs/inference/bin/pip install torch transformers accelerate peft bitsandbytes \
    fastapi uvicorn pydantic

# 2. 下载基座模型到 /root/models/（LoRA 权重是增量，必须配基座模型）
#    Hugging Face:   huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir /root/models/Qwen2.5-7B-Instruct
#    国内用 ModelScope: modelscope snapshot_download('Qwen/Qwen2.5-7B-Instruct', cache_dir='/root/models')

# 3. 启动（默认端口 8002），日志在 deploy/inference/inference_server.log
bash start_server.sh

# 4. 验证
curl http://localhost:8002/health
curl -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-7b-lora","messages":[{"role":"user","content":"hi"}]}'
```

### 9.3 注册到后端（Windows 端）

推理服务起来后，在 Windows 端把它的地址写进数据库（`model_providers` 表）：

```bash
cd backend
python scripts/register_lora_provider.py                # 自动探测 WSL2 IP，推荐
python scripts/register_lora_provider.py --dry-run      # 只预览不修改
python scripts/register_lora_provider.py --host <ip>    # 自动探测失败时手动指定
```

探测优先级：`--host` 参数 > `LORA_INFERENCE_HOST` 环境变量（可放 `.env`）> 自动探测 WSL2 IP > 回退 `127.0.0.1`。

**常见坑**：默认 WSL 发行版是 docker-desktop 时会探测不到 Ubuntu 的 IP，脚本会自动跳过 docker 发行版再探测；仍失败就手动 `wsl hostname -I` 查到 IP 后 `--host` 指定。

---

_有问题联系后端维护者。更新依赖或迁移后，请同步更新这份文件。_
