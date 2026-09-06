"""注册本地 Ollama 承载的 Qwen2.5-7B LoRA 推理服务到模型网关。

用法（在 backend/ 目录执行）:
    python scripts/register_ollama_provider.py            # 正式注册
    python scripts/register_ollama_provider.py --dry-run  # 仅预览，不修改
    python scripts/register_ollama_provider.py --bind     # 同时把 deep_learning_001 课程绑定到该供应商

说明:
    - 该供应商指向 Ollama 服务（http://localhost:11434/v1），模型 qwen2.5-7b-lora。
    - 默认只新增供应商、不修改课程绑定；确认推理效果后再用 --bind 切换课程。
    - 与 register_lora_provider.py 的区别：注册的是 Ollama 运行时（支持流式输出）。
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

from sqlalchemy import select, text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.model_gateway import ModelProvider  # noqa: E402

PROVIDER_ID = "qwen25-lora-ollama"
PROVIDER_DISPLAY_NAME = "Qwen2.5-7B LoRA (Ollama)"
CHAT_MODEL = "qwen2.5-7b-lora"
BASE_URL = "http://localhost:11434/v1"
COURSE_SLUG = "deep_learning_001"


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def register_provider(*, dry_run: bool, bind: bool) -> dict:
    """注册 Ollama 供应商，可选绑定课程。"""
    db = SessionLocal()
    stats: dict = {"provider": None, "course": None, "base_url": BASE_URL}
    try:
        existing = db.execute(
            select(ModelProvider).where(ModelProvider.provider == PROVIDER_ID)
        ).scalar_one_or_none()

        if existing:
            print(f"供应商 {PROVIDER_ID} 已存在，更新配置...")
            if not dry_run:
                existing.base_url = BASE_URL
                existing.chat_model = CHAT_MODEL
                existing.display_name = PROVIDER_DISPLAY_NAME
                existing.is_active = True
                existing.health_status = "standby"
                # Ollama 支持流式输出；工具调用/JSON 模式保持关闭
                existing.supports_stream = True
                existing.supports_tool_call = False
                existing.supports_json_mode = False
                existing.priority = 3
                db.flush()
            stats["provider"] = "updated"
        else:
            print(f"创建供应商 {PROVIDER_ID}...")
            if not dry_run:
                provider_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, PROVIDER_ID))
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
                        "base_url": BASE_URL,
                        "protocol": "openai_compatible",
                        "api_key": "sk-local",
                        "chat_model": CHAT_MODEL,
                        "embedding_model": None,
                        "supports_stream": True,
                        "supports_tool_call": False,
                        "supports_json_mode": False,
                        "health_status": "standby",
                        "priority": 3,
                        "is_active": True,
                        "is_default": False,
                        "meta": dumps({"source": "ollama_deploy", "seed": False}),
                    },
                )
                db.flush()
            stats["provider"] = "created"

        # 健康检查记录（如不存在则创建）
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
                        },
                    )

        # 可选：绑定课程
        if bind:
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
        else:
            stats["course"] = "not bound (--bind to bind course)"

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
    parser.add_argument("--bind", action="store_true", help="同时把课程绑定到该供应商")
    args = parser.parse_args()

    result = register_provider(dry_run=args.dry_run, bind=args.bind)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not args.dry_run:
        print()
        print("=" * 50)
        print("注册完成！")
        print(f"  供应商: {PROVIDER_ID}")
        print(f"  地址: {BASE_URL}")
        print(f"  模型: {CHAT_MODEL}")
        print("  绑定课程: " + ("已绑定" if args.bind else "未绑定（确认后加 --bind 切换）"))
        print("=" * 50)


if __name__ == "__main__":
    main()
