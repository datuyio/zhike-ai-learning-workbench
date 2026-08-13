#!/bin/bash
# 启动 LoRA 推理服务（在 WSL2 内运行，需 GPU）
#
# 可配置项（环境变量，均可省略）：
#   SB_VENV      Python 虚拟环境路径，默认 $HOME/venvs/inference
#   SB_DIR       推理服务代码目录，默认本脚本所在目录（仓库 deploy/inference/）
#   LORA_PORT    服务端口，默认 8002
#   LORA_LOG     日志文件路径，默认 $SB_DIR/inference_server.log
#
# 首次使用（以 Ubuntu、root 用户为例）：
#   sudo apt-get update
#   sudo apt-get install -y python3.11-venv        # 按系统 Python 版本调整
#   python3 -m venv /root/venvs/inference
#   /root/venvs/inference/bin/pip install torch transformers accelerate peft \
#       bitsandbytes fastapi uvicorn pydantic   # 如需 CUDA 版 torch 请按官网方式安装

set -e

SB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SB_VENV="${SB_VENV:-$HOME/venvs/inference}"
LORA_LOG="${LORA_LOG:-$SB_DIR/inference_server.log}"

source "$SB_VENV/bin/activate"
cd "$SB_DIR"

# 启动前先清理旧进程（避免端口占用）
if [ -f "${SB_DIR}/server.pid" ]; then
    OLD_PID=$(cat "${SB_DIR}/server.pid")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "停止旧推理服务 (PID $OLD_PID)..."
        kill "$OLD_PID"
        sleep 2
    fi
    rm -f "${SB_DIR}/server.pid"
fi

nohup python inference_server.py > "$LORA_LOG" 2>&1 &
echo $! > "${SB_DIR}/server.pid"
echo "推理服务已启动，PID $(cat "${SB_DIR}/server.pid")"
echo "日志: $LORA_LOG"