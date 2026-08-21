# LoRA 推理服务（T-B-11）

本地 Qwen2.5-7B-Instruct + LoRA 微调模型的微调训练与推理服务。推理服务提供 OpenAI 兼容的 `/v1/chat/completions` API，运行在 **WSL2 / Linux（需 GPU）**。

> 部署操作步骤请看 [`backend/SETUP.md` 第 9 节](../../backend/SETUP.md#9-lora-推理服务部署t-b-11需要-gpu)，本文件详细说明环境变量、数据准备和目录结构。

---

## 目录结构

```
deploy/inference/
├── README.md                    # 本文件
├── inference_server.py          # 推理服务主程序（FastAPI，端口默认 8002）
├── start_server.sh              # 启动脚本（WSL2 内运行）
├── qlora_train.py               # QLoRA 微调训练脚本
├── qa_data_all.jsonl            # ⚠️ 训练数据（7053 条 QA 对），不放仓库，需自行准备
├── lora_output/                 # 训练中间输出（训练时自动生成）
├── lora_weights_final/          # 微调好的 LoRA 适配器权重（已入库 ~88MB）
│   ├── adapter_config.json
│   ├── adapter_model.safetensors   # ~80MB
│   ├── tokenizer.json
│   └── ...
└── start_server.sh              # 启动脚本
```

---

## 环境变量

所有路径均可通过环境变量覆盖，拉到别人电脑上时只需改环境变量，**不要改脚本本身**。

### 训练脚本（qlora_train.py）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MODELS_ROOT` | `/root/models` | 基座模型存放目录（与推理服务统一） |
| `QWEN_MODEL_NAME` | `Qwen2.5-7B-Instruct` | 基座模型文件夹名 |
| `TRAIN_DATA_PATH` | `./qa_data_all.jsonl` | 训练数据（7053 条 QA 对 JSONL） |
| `LORA_OUTPUT_DIR` | `./lora_output` | 训练中间输出目录 |
| `LORA_WEIGHTS_DIR` | `./lora_weights_final` | 最终 LoRA 权重输出目录 |

### 推理服务（inference_server.py + start_server.sh）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MODELS_ROOT` | `/root/models` | 基座模型存放目录 |
| `QWEN_MODEL_NAME` | `Qwen2.5-7B-Instruct` | 基座模型文件夹名 |
| `LORA_PATH` | 本目录下 `lora_weights_final/` | LoRA 权重路径 |
| `LORA_PORT` | `8002` | 推理服务监听端口 |
| `SB_VENV`（启动脚本用） | `$HOME/venvs/inference` | Python 虚拟环境路径 |
| `LORA_LOG`（启动脚本用） | 同目录 `inference_server.log` | 日志文件路径 |

---

## 训练数据准备

### 教材来源

LoRA 微调使用了以下 5 本教材，从中提取文本并生成 QA 对：

| 书名 | 作者 | 提取输出文件名 |
|------|------|----------------|
| 《机器学习》 | 周志华 | `ml_zhouzhihua_raw.txt` |
| 《统计学习方法》 | 李航 | `statistical_learning_lihang_raw.txt` |
| 《深度学习》（花书） | Ian Goodfellow 等 | `deep_learning_goodfellow_raw.txt` |
| Deep Learning Notes | — | `deep_learning_notes_raw.txt` |
| Pattern Recognition and Machine Learning | Christopher M. Bishop | `prml_bishop_raw.txt` |

### 数据生成流程（参考用，不需要重复做）

数据准备的全套脚本在 `E:\testing\TB10\`（仅本机，不放仓库），流程如下：

```
PDF 教材 → extract_text.py（PyMuPDF 提取文本）
         → chunk_and_prompt.py（智能切块 + 构造 QA 生成 prompt）
         → 大模型生成 QA 对
         → merge_qa.py（合并去重）
         → qa_data_all.jsonl（7053 条，Alpaca 格式）
```

### 如果要重新训练

1. 准备好 5 本教材的 PDF
2. 按上述流程提取文本并生成 QA 对
3. 把生成的 `qa_data_all.jsonl` 放到 `deploy/inference/` 目录下
4. 下载基座模型（见下文）

---

## 微调训练

训练在 WSL2 / Linux 中进行（需要 GPU），LoRA 权重已预训练好（在仓库里），**大多数情况下不需要重新训练**。

如果需要重新训练：

```bash
cd deploy/inference

# 1. 确保基座模型已下载（见下文）
# 2. 确保训练数据 qa_data_all.jsonl 已就位
# 3. 运行训练
python qlora_train.py
```

训练完成后，LoRA 权重会保存到 `lora_weights_final/` 目录。

---

## 基座模型下载

LoRA 权重是增量，必须配合基座模型 `Qwen/Qwen2.5-7B-Instruct` 使用（约 15GB）。

```bash
# Hugging Face
huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir /root/models/Qwen2.5-7B-Instruct

# 国内用 ModelScope
# python -c "from modelscope import snapshot_download; snapshot_download('Qwen/Qwen2.5-7B-Instruct', cache_dir='/root/models')"
```

下载后设 `MODELS_ROOT=/root/models`（默认值），推理服务和训练脚本会自动找到模型。

---

## 推理服务启动

```bash
# 进入推理服务目录
cd deploy/inference

# 1. 建虚拟环境装依赖
python3.11 -m venv /root/venvs/inference
/root/venvs/inference/bin/pip install torch transformers accelerate peft bitsandbytes \
    fastapi uvicorn pydantic

# 2. 启动（默认端口 8002）
bash start_server.sh

# 3. 验证
curl http://localhost:8002/health
curl -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-7b-lora","messages":[{"role":"user","content":"什么是梯度下降？"}]}'
```

---

## 注册到后端

推理服务起来后，在 Windows 端把它的地址写进数据库（`model_providers` 表）：

```bash
cd backend
python scripts/register_lora_provider.py --dry-run      # 先预览
python scripts/register_lora_provider.py                # 正式注册
python scripts/register_lora_provider.py --host <ip>    # 自动探测失败时手动指定
```

探测优先级：`--host` 参数 > `LORA_INFERENCE_HOST` 环境变量（可放 `.env`）> 自动探测 WSL2 IP > 回退 `127.0.0.1`。

---

## 拉取到新电脑的联调准备清单

给 C 同学或其他协作者参考：

| 步骤 | 做什么 | 时间 |
|------|--------|------|
| 1 | 拉取仓库代码 | — |
| 2 | 安装 Docker 并 `docker compose up --build` 启动后端（见 `backend/SETUP.md`） | ~10min |
| 3 | 下载 Qwen2.5-7B-Instruct 基座模型（15GB）到 `/root/models/` | ~30min（看网速） |
| 4 | 建 WSL 虚拟环境，装 torch 等依赖 | ~10min |
| 5 | 启动推理服务 `bash start_server.sh` | — |
| 6 | 注册推理服务 `python register_lora_provider.py` | — |
| 7 | 验证 `curl http://localhost:8002/health` 返回 ok | — |

**不需要做的事**：
- 不需要重新训练 LoRA（权重已入库）
- 不需要准备 7053 条 QA 数据（除非要重新训练）
- 不需要下载 5 本教材 PDF（除非要重新生成数据）