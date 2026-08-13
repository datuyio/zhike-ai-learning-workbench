"""Qwen2.5-7B-Instruct + LoRA 推理服务（简化方案）
- 4-bit NF4 量化加载基座模型（同训练时）
- 加载 LoRA 微调权重
- 提供 OpenAI 兼容的 /v1/chat/completions API
- 端口 8002
"""
import os
import time
from typing import Optional, List

os.environ.setdefault("PYTORCH_JIT", "0")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import PeftModel

# 可配置路径/端口，均可通过环境变量覆盖（见 README）
# MODELS_ROOT: 基座模型目录，默认 /root/models，模型文件夹名需为 QWEN_MODEL_NAME
# LORA_PATH:   LoRA 微调权重目录，默认取本文件同级 lora_weights_final/（即本仓库 deploy/inference/）
MODELS_ROOT = os.environ.get("MODELS_ROOT", "/root/models")
QWEN_MODEL_NAME = os.environ.get("QWEN_MODEL_NAME", "Qwen2.5-7B-Instruct")
MODEL_PATH = os.path.join(MODELS_ROOT, QWEN_MODEL_NAME)
LORA_PATH = os.environ.get(
    "LORA_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "lora_weights_final"),
)
PORT = int(os.environ.get("LORA_PORT", "8002"))

model = None
tokenizer = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "qwen2.5-7b-lora"
    messages: List[ChatMessage]
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024
    stream: bool = False

app = FastAPI(title="Qwen2.5-7B LoRA")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def load_model():
    global model, tokenizer
    print("加载 Tokenizer...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True, padding_side="right")
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("加载 4-bit 量化模型...", flush=True)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=False,
    )
    base = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, quantization_config=bnb_config, device_map={"": 0},
        torch_dtype=torch.bfloat16, trust_remote_code=True, use_cache=True,
    )

    print("加载 LoRA 权重...", flush=True)
    model = PeftModel.from_pretrained(base, LORA_PATH)
    model.eval()
    print("模型加载完成！", flush=True)

@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": [{"id": "qwen2.5-7b-lora", "object": "model", "created": int(time.time()), "owned_by": "user"}]}

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}

@app.post("/v1/chat/completions")
def chat(req: ChatCompletionRequest):
    if model is None or tokenizer is None:
        raise HTTPException(503, "模型未加载完成")
    if req.stream:
        raise HTTPException(400, "暂不支持流式输出")

    try:
        msgs = [{"role": m.role, "content": m.content} for m in req.messages]
        text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=2048).to("cuda")

        with torch.no_grad():
            outputs = model.generate(
                **inputs, max_new_tokens=req.max_tokens,
                temperature=req.temperature, top_p=req.top_p, do_sample=True,
                pad_token_id=tokenizer.eos_token_id, eos_token_id=tokenizer.eos_token_id,
            )

        input_len = inputs["input_ids"].shape[1]
        response_text = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True)

        return {
            "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion",
            "created": int(time.time()), "model": req.model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": response_text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": input_len, "completion_tokens": len(outputs[0]) - input_len, "total_tokens": len(outputs[0])},
        }
    except Exception as e:
        raise HTTPException(500, str(e))

if __name__ == "__main__":
    print(f"启动推理服务，端口 {PORT}...", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
