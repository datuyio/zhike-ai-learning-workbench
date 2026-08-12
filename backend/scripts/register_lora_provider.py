"""注册本地 Qwen2.5-7B LoRA 推理服务到模型网关。

使用方法:
  1. 确保 Docker Desktop 已在运行 (docker compose up -d postgres)
  2. 确保 WSL2 推理服务已启动 (port 8002)
  3. 在 backend/ 目录执行:
     python scripts/register_lora_provider.py
     python scripts/register_lora_provider.py --dry-run  (仅预览，不修改)

本脚本会:
  - 在 model_providers 表中创建 qwen25-lora-local 供应商
  - 将 deep_learning_001 课程的 chat_provider 指向该供应商
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.models.model_gateway import ModelProvider
from app.models.course import Course
from sqlalchemy import select, text

# ============== 配置 ==============
# 推理服务地址（WSL2 IP + 端口 8002）
WSL_IP = "172.27.195.47"
LORA_BASE_URL = f"http://{WSL_IP}:8002/v1"

# 供应商唯一标识
PROVIDER_ID = "qwen25-lora-local"
PROVIDER_DISPLAY_NAME = "Qwen2.5-7B LoRA (本地)"
CHAT_MODEL = "qwen2.5-7b-lora"

# 要绑定的课程
COURSE_SLUG = "deep_learning_001"


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def register_provider(*, dry_run: bool) -> dict:
    """注册 LoRA 供应商并绑定到课程。"""
    db = SessionLocal()
    stats: dict = {"provider": None, "course": None}
    try:
        # ---- 1. 创建/更新供应商 ----
        existing = db.execute(
            select(ModelProvider).where(ModelProvider.provider == PROVIDER_ID)
        ).scalar_one_or_none()

        if existing:
            print(f"供应商 {PROVIDER_ID} 已存在，更新配置...")
            if not dry_run:
                existing.base_url = LORA_BASE_URL
                existing.chat_model = CHAT_MODEL
                existing.display_name = PROVIDER_DISPLAY_NAME
                existing.is_active = True
                existing.health_status = "standby"
                existing.supports_stream = False
                existing.supports_tool_call = False
                existing.supports_json_mode = False
                existing.priority = 3
                # 不打乱其他字段
                db.flush()
            stats["provider"] = "updated"
        else:
            print(f"创建供应商 {PROVIDER_ID}...")
            if not dry_run:
                provider_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, PROVIDER_ID))
                # 使用 raw SQL 插入，确保与 seed 数据一致
                db.execute(
                    text("""
                        INSERT INTO model_providers (
                            id, provider, display_name, provider_type,
                            base_url, protocol, api_key_encrypted,
                            chat_model, embedding_model,
                            supports_stream, supports_tool_call, supports_json_mode,
                            health_status, priority, is_active, is_default,
                            meta_json
                        ) VALUES (
                            :id, :provider, :display_name, :provider_type,
                            :base_url, :protocol, :api_key,
                            :chat_model, :embedding_model,
                            :supports_stream, :supports_tool_call, :supports_json_mode,
                            :health_status, :priority, :is_active, :is_default,
                            CAST(:meta AS JSONB)
                        )
                        ON CONFLICT (provider) DO UPDATE SET
                            base_url = EXCLUDED.base_url,
                            chat_model = EXCLUDED.chat_model,
                            display_name = EXCLUDED.display_name,
                            is_active = EXCLUDED.is_active,
                            health_status = EXCLUDED.health_status,
                            supports_stream = EXCLUDED.supports_stream,
                            supports_tool_call = EXCLUDED.supports_tool_call,
                            supports_json_mode = EXCLUDED.supports_json_mode,
                            priority = EXCLUDED.priority
                    """),
                    {
                        "id": provider_id,
                        "provider": PROVIDER_ID,
                        "display_name": PROVIDER_DISPLAY_NAME,
                        "provider_type": "chat",
                        "base_url": LORA_BASE_URL,
                        "protocol": "openai_compatible",
                        "api_key": "sk-local",
                        "chat_model": CHAT_MODEL,
                        "embedding_model": None,
                        "supports_stream": False,
                        "supports_tool_call": False,
                        "supports_json_mode": False,
                        "health_status": "standby",
                        "priority": 3,
                        "is_active": True,
                        "is_default": False,
                        "meta": dumps({"source": "lora_deploy", "seed": False}),
                    }
                )
                db.flush()
            stats["provider"] = "created"

        # ---- 2. 创建健康检查记录（如果不存在） ----
        if not dry_run:
            provider_row = db.execute(
                select(ModelProvider).where(ModelProvider.provider == PROVIDER_ID)
            ).scalar_one_or_none()
            if provider_row:
                health_exists = db.execute(
                    text("SELECT 1 FROM model_provider_health WHERE provider_id = :pid"),
                    {"pid": provider_row.id},
                ).scalar_one_or_none()
                if not health_exists:
                    db.execute(
                        text("""
                            INSERT INTO model_provider_health (id, provider_id, status, success_rate, avg_latency_ms, consecutive_failures)
                            VALUES (gen_random_uuid(), :provider_id, :status, :success_rate, :avg_latency_ms, :failures)
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "provider_id": provider_row.id,
                            "status": "standby",
                            "success_rate": 1.0,
                            "avg_latency_ms": 0,
                            "failures": 0,
                        }
                    )

        # ---- 3. 绑定课程 ----
        course = db.execute(
            select(Course).where(Course.slug == COURSE_SLUG)
        ).scalar_one_or_none()

        if not course:
            print(f"警告: 未找到课程 {COURSE_SLUG}，跳过绑定")
            stats["course"] = "skipped (not found)"
        else:
            config = dict(course.model_config_json or {})
            old_provider = config.get("chat_provider")
            config["chat_provider"] = PROVIDER_ID
            if not dry_run:
                course.model_config_json = config
                db.flush()
            stats["course"] = {
                "slug": COURSE_SLUG,
                "old_chat_provider": old_provider,
                "new_chat_provider": PROVIDER_ID,
            }

        if dry_run:
            db.rollback()
            stats["dry_run"] = True
            print("[DRY RUN] 未修改任何数据")
        else:
            db.commit()
            print("已提交所有修改")

        return stats

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不修改数据库")
    args = parser.parse_args()

    result = register_provider(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not args.dry_run:
        print()
        print("=" * 50)
        print("注册完成！")
        print(f"  供应商: {PROVIDER_ID}")
        print(f"  地址: {LORA_BASE_URL}")
        print(f"  模型: {CHAT_MODEL}")
        print(f"  课程绑定: {COURSE_SLUG}")
        print()
        print("后续操作：")
        print("  1. 启动 Docker Desktop")
        print("  2. 启动后端: docker compose up -d backend")
        print("  3. 在后台管理界面检查供应商状态")
        print("=" * 50)


if __name__ == "__main__":
    main()