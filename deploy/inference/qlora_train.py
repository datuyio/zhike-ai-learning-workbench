"""
Qwen2.5-7B-Instruct QLoRA 微调脚本
- 4-bit NF4 量化（bitsandbytes）
- LoRA: r=8, alpha=16
- 训练数据: T-B-10 QA 数据（Alpaca 格式，7053 条）
- 输出: LoRA 权重到 lora_output/ 目录
"""
import os
import sys
import json

# Blackwell(sm_120) 上 torch.compile / dynamo 的首次 JIT 编译极慢，
# 会拖慢甚至卡死训练。这里强制走 eager 模式并关闭相关编译缓存。
os.environ.setdefault("PYTORCH_JIT", "0")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
# 关闭 SDPA 的 flash-attention JIT 编译路径（Blackwell 上易触发慢编译）
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

import torch
# 禁用 dynamo 编译，确保走 eager 模式（避免 Blackwell 首次 JIT 编译极慢）
try:
    torch._dynamo.config.suppress_errors = True
except Exception:
    pass
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    PeftModel,
)

# ============== 配置（均可通过环境变量覆盖，详见 README） ==============
# BASE_DIR: 本脚本所在目录（deploy/inference/），作为相对路径的基准
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 基座模型路径：默认 /root/models/Qwen2.5-7B-Instruct（与推理服务 inference_server.py 一致）
MODELS_ROOT = os.environ.get("MODELS_ROOT", "/root/models")
QWEN_MODEL_NAME = os.environ.get("QWEN_MODEL_NAME", "Qwen2.5-7B-Instruct")
MODEL_PATH = os.path.join(MODELS_ROOT, QWEN_MODEL_NAME)

# 训练数据：7053 条 QA 对（Alpaca 格式），不放仓库，需自行准备
DATA_PATH = os.environ.get("TRAIN_DATA_PATH", os.path.join(BASE_DIR, "qa_data_all.jsonl"))
# 输出目录：默认在本脚本同级目录下，避免写死盘符
OUTPUT_DIR = os.environ.get("LORA_OUTPUT_DIR", os.path.join(BASE_DIR, "lora_output"))
SAVE_WEIGHTS_DIR = os.environ.get("LORA_WEIGHTS_DIR", os.path.join(BASE_DIR, "lora_weights_final"))

# QLoRA 超参数
LORA_R = 8
LORA_ALPHA = 16
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

# 训练超参数
BATCH_SIZE = 1          # 8GB 显存，必须 batch_size=1
GRAD_ACCUM_STEPS = 8    # 等效 batch_size = 8
LEARNING_RATE = 2e-4
NUM_EPOCHS = 1          # 1 个 epoch（与实测训练记录一致：838 步 / 13 小时 21 分钟）
MAX_SEQ_LEN = 1024      # 最大序列长度
WARMUP_RATIO = 0.03
LOGGING_STEPS = 10
SAVE_STEPS = 200
EVAL_STEPS = 200

# ============== 加载 Tokenizer ==============
print("[1/7] 加载 Tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True,
    padding_side="right",
)
# Qwen2.5 通常没有 pad_token，设为 eos_token
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# ============== 加载数据 ==============
print("[2/7] 加载训练数据...")
records = []
with open(DATA_PATH, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

print(f"  共加载 {len(records)} 条记录")

# 转换为 Alpaca 训练格式
def format_alpaca(example):
    """将 Alpaca 格式转为模型输入"""
    if example["input"] and example["input"].strip():
        prompt = f"<|im_start|>user\n{example['instruction']}\n{example['input']}<|im_end|>\n<|im_start|>assistant\n"
    else:
        prompt = f"<|im_start|>user\n{example['instruction']}<|im_end|>\n<|im_start|>assistant\n"
    full_text = prompt + example["output"] + "<|im_end|>"
    return {"prompt": prompt, "full_text": full_text}

formatted = [format_alpaca(r) for r in records]

# 划分训练/验证集（95% / 5%）
split_idx = int(len(formatted) * 0.95)
train_data = formatted[:split_idx]
eval_data = formatted[split_idx:]
print(f"  训练集: {len(train_data)} 条, 验证集: {len(eval_data)} 条")

train_dataset = Dataset.from_list(train_data)
eval_dataset = Dataset.from_list(eval_data)

# ============== 分词处理 ==============
def tokenize_fn(examples):
    """对训练文本进行分词"""
    model_inputs = tokenizer(
        examples["full_text"],
        max_length=MAX_SEQ_LEN,
        truncation=True,
        padding=False,
        return_tensors=None,
    )
    # 复制 input_ids 作为 labels（因果语言模型）
    model_inputs["labels"] = model_inputs["input_ids"].copy()
    return model_inputs

print("[3/7] 分词处理...")
train_dataset = train_dataset.map(
    tokenize_fn,
    remove_columns=["prompt", "full_text"],
    desc="分词训练集",
)
eval_dataset = eval_dataset.map(
    tokenize_fn,
    remove_columns=["prompt", "full_text"],
    desc="分词验证集",
)

# ============== 4-bit 量化配置 ==============
print("[4/7] 配置 4-bit 量化...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

# ============== 加载模型 ==============
print("[5/7] 加载 Qwen2.5-7B-Instruct 模型（4-bit）...")
# 必须显式指定 device_map={'': 0}，不能用 'auto'（内存不足会导致段错误）
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    quantization_config=bnb_config,
    device_map={"": 0},  # 显式放到 GPU 0
    torch_dtype=torch.bfloat16,
    trust_remote_code=True,
    use_cache=False,  # 训练时关闭 KV cache
)

# 为 kbit 训练准备模型
model = prepare_model_for_kbit_training(model)

# ============== LoRA 配置 ==============
print("[6/7] 配置 LoRA...")
lora_config = LoraConfig(
    r=LORA_R,
    lora_alpha=LORA_ALPHA,
    target_modules=TARGET_MODULES,
    lora_dropout=LORA_DROPOUT,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ============== 训练参数 ==============
print("[7/7] 开始训练...")
training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACCUM_STEPS,
    gradient_checkpointing=True,
    learning_rate=LEARNING_RATE,
    warmup_ratio=WARMUP_RATIO,
    lr_scheduler_type="cosine",
    bf16=True,  # RTX 5060 支持 bf16
    logging_steps=LOGGING_STEPS,
    save_steps=SAVE_STEPS,
    eval_steps=EVAL_STEPS,
    eval_strategy="steps",
    save_strategy="steps",
    save_total_limit=2,  # 只保留最近 2 个 checkpoint
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    report_to="none",  # 不上报 wandb
    dataloader_num_workers=0,  # Windows 下设为 0 避免多进程问题
    ddp_find_unused_parameters=False,
)

data_collator = DataCollatorForSeq2Seq(
    tokenizer=tokenizer,
    model=model,
    padding="longest",
    max_length=MAX_SEQ_LEN,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    data_collator=data_collator,
    processing_class=tokenizer,
)

# ============== 训练 ==============
trainer.train()

# ============== 保存 LoRA 权重 ==============
print(f"\n保存 LoRA 权重到 {SAVE_WEIGHTS_DIR} ...")
os.makedirs(SAVE_WEIGHTS_DIR, exist_ok=True)
model.save_pretrained(SAVE_WEIGHTS_DIR)
tokenizer.save_pretrained(SAVE_WEIGHTS_DIR)
print("Done! LoRA 权重已保存。")