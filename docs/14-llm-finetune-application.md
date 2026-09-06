# 微调模型应用说明（Qwen2.5-7B + LoRA）

> 任务编号：T-B-11（训练与推理服务）/ T-B-14（评估）
> 本文件梳理微调模型在「智课 AI 个性化学习工作台」中的完整应用链路：从教材语料到 QA 数据、从 QLoRA 训练到推理服务、从模型网关注册到课程绑定与实际调用。
> 配套评估报告见 `docs/15-llm-finetune-evaluation-report.md`。

---

## 1. 定位与价值

系统默认通过模型网关调用云端大模型 API（DeepSeek / 通义 / 讯飞星火 / 智谱等）即可完整运行。本地微调模型是**学科垂类增强**的可选部署项：

- **目标**：让通用大模型（Qwen2.5-7B-Instruct）的回答风格与知识密度贴近**教材 QA 场景**，更适合作业辅导与学习问答；
- **方式**：用 5 本经典 AI/ML 教材构造的 7053 条 QA 对做 QLoRA 微调，产出仅 **0.264% 参数量的增量权重**（约 2018 万参数）；
- **成本**：4-bit NF4 量化后可在 **8GB 显存**的消费级笔记本 GPU 上训练与推理。

## 2. 应用链路总览

```text
5 本教材 PDF（周志华/李航/花书/DL Notes/PRML）
   ↓ PyMuPDF 提取 + MinerU OCR + 智能切块 + 大模型生成 QA + 合并去重
7053 条 Alpaca 格式 QA 对（qa_data_all.jsonl，仅存训练机 E:\testing\TB10\）
   ↓ qlora_train.py（QLoRA 4-bit NF4 + LoRA r=8/alpha=16）
LoRA 适配器权重（deploy/inference/lora_weights_final/，约 88MB，随仓库分发）
   ↓ inference_server.py（FastAPI，OpenAI 兼容 /v1/chat/completions，端口 8002）
本地推理服务（需 WSL2/Linux + GPU，基座模型 Qwen2.5-7B-Instruct 需自行下载）
   ↓ register_lora_provider.py（写入 model_providers 表）
模型网关新供应商 qwen25-lora-local（"Qwen2.5-7B LoRA (本地)"）
   ↓ 课程绑定 deep_learning_001.chat_provider
学生在该课程内的 AI 对话 → AiOrchestratorService → ModelGateway → 本地推理服务
   ↓ 每次调用写入 model_call_logs，可在网关中心观测
run_lora_eval.py / run_base_eval.py（17 道题评测，结果随仓库分发）
   ↓
docs/15-llm-finetune-evaluation-report.md（评估报告）
```

## 3. 数据链路（T-B-10 产物）

| 教材 | 作者 | QA 条数 | 占比 |
|------|------|--------:|-----:|
| PRML | Christopher M. Bishop | 3329 | 47.2% |
| Deep Learning Notes | — | 1388 | 19.7% |
| 《机器学习》 | 周志华 | 1196 | 17.0% |
| 《统计学习方法》 | 李航 | 650 | 9.2% |
| 《深度学习》（花书） | Ian Goodfellow 等 | 490 | 6.9% |
| **合计** | | **7053** | **100%** |

数据质量：零解析失败、零重复、零过短；instruction 均值 30.7 字符、output 均值 123.1 字符，长度分布合理。

## 4. 训练（qlora_train.py）

| 配置项 | 值 |
|---|---|
| 环境 | WSL2 Ubuntu-24.04 / RTX 5060 Laptop（8GB VRAM）/ PyTorch 2.10 + CUDA 12.8 |
| 量化 | 4-bit NF4（BitsAndBytes），模型占显存 ~4.5GB |
| LoRA | r=8, alpha=16, dropout=0.05，目标全部线性层，可训练参数 20,185,088（0.264%） |
| 超参数 | batch=1 + grad_accum=8（等效 8）、max_seq_len=1024、lr=2e-4（余弦衰减）、bf16、1 epoch、838 步 |
| 耗时 | 13 小时 21 分钟（平均 57.4 秒/步） |
| 结果 | Loss 3.572 → 1.730（降幅 51.6%），验证 loss 1.701 < 训练 loss 1.933，梯度范数稳定 0.89–1.42，无过拟合迹象 |

## 5. 推理服务（deploy/inference/inference_server.py）

- **框架**：FastAPI + Uvicorn，监听 `0.0.0.0:8002`（默认）；
- **加载**：4-bit NF4 量化加载基座 + `PeftModel` 合并 LoRA 权重；
- **协议**：OpenAI 兼容 `POST /v1/chat/completions`（model=`qwen2.5-7b-lora`），另有 `/health`、`/v1/models`；
- **环境变量**：`MODELS_ROOT`（基座目录，默认 `/root/models`）、`QWEN_MODEL_NAME`、`LORA_PATH`（默认本目录 `lora_weights_final/`）、`LORA_PORT`；
- **已知限制**：不支持流式输出（stream=false）、transformers 原生推理（平均 5.7s）、仅监听不对外暴露。

## 6. 系统集成（backend/scripts/register_lora_provider.py）

一键注册脚本完成两步：

1. **创建供应商**：`model_providers` 表插入/更新
   - `provider = qwen25-lora-local`，显示名「Qwen2.5-7B LoRA (本地)」
   - `protocol = openai_compatible`，`base_url = http://{host}:8002/v1`，`chat_model = qwen2.5-7b-lora`
   - 能力标记：`supports_stream=false`、`supports_tool_call=false`、`supports_json_mode=false`（低能力供应商，编排层会走更严格的后端校验与降级）
   - `priority=3`，`health_status=standby`（随后由网关健康检查接管）
2. **绑定课程**：`deep_learning_001` 课程的 `model_config_json.chat_provider` 指向该供应商

地址探测优先级：`--host` 参数 > `LORA_INFERENCE_HOST` 环境变量 > 自动探测 WSL2 IP（排除 docker-desktop）> `127.0.0.1`。

## 7. 实际调用链路

```text
学生在 deep_learning_001 课程提问
   → POST /api/v1/ai/messages（或 WebSocket /ws/ai/{conversation_id}）
   → AiOrchestratorService.handle_message
       → CourseAiBindingService 解析课程绑定（chat_provider = qwen25-lora-local）
       → ModelGateway 供应商链选择本地供应商
       → httpx 转发 http://<host>:8002/v1/chat/completions
   → 回答 + trace 返回前端
   → model_call_logs 记录调用（供应商/模型/耗时/用量），网关中心可观测
```

注：该供应商 `supports_stream=false`，对话经 HTTP 一次性返回；前端如走 WebSocket 通道，编排层会按供应商能力降级为非流式。

## 8. 效果评估（详见评估报告）

- **17 道题（5 领域）人工评测**：全部成功返回，无明显错误；
- **风格变化**：从"百科式长篇"（基座 300 tokens 截断）变为"教材 QA 式精炼"（平均 87 tokens 自然结束）；
- **性能**：平均响应 5.7s（基座 10.6s），显存 ~4.5GB，满足学习问答场景；
- **集成验证**：健康检查通过、`model_call_logs` 确认对话走本地模型。

## 9. 部署与复现步骤

```bash
# 1. 下载基座模型（约 15GB，LoRA 是增量必须叠加基座）
huggingface-cli download Qwen/Qwen2.5-7B-Instruct --local-dir /root/models/Qwen2.5-7B-Instruct
#   国内可用 ModelScope：modelscope download --model Qwen/Qwen2.5-7B-Instruct

# 2. 建虚拟环境装依赖（WSL2/Linux + GPU）
python3.11 -m venv /root/venvs/inference
/root/venvs/inference/bin/pip install torch transformers accelerate peft bitsandbytes fastapi uvicorn pydantic

# 3. 启动推理服务（默认 8002）
cd deploy/inference && bash start_server.sh
curl http://localhost:8002/health   # {"status":"ok"}

# 4. 注册到后端模型网关（Windows 端）
cd backend
python scripts/register_lora_provider.py --dry-run   # 先预览
python scripts/register_lora_provider.py             # 正式注册并绑定课程

# 5. 验证
curl -X POST http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-7b-lora","messages":[{"role":"user","content":"什么是梯度下降？"}]}'
```

> 不需要重新训练（权重已入库）；不需要 7053 条数据（除非重新训练）；不需要 5 本教材 PDF（除非重新生成数据）。

## 10. 已知限制与改进方向

| 限制 | 改进方向 |
|---|---|
| 不支持流式输出 | 升级 SSE / WebSocket 流式 |
| 推理 5.7s 偏慢（transformers 原生） | 引入 vLLM / TGI 推理框架 |
| 仅 1 epoch | 尝试 2–3 epoch 并监控过拟合 |
| 仅覆盖 5 本教材 | 扩充教材与领域 |
| 人工评测 | 引入 BLEU / ROUGE / BERTScore 自动指标 |
| 基座模型需自行下载（15GB） | 提供 Docker 化一键部署镜像 |

---

*关联文件：`deploy/inference/README.md`、`deploy/inference/qlora_train.py`、`deploy/inference/inference_server.py`、`deploy/inference/start_server.sh`、`backend/scripts/register_lora_provider.py`、`docs/15-llm-finetune-evaluation-report.md`*
