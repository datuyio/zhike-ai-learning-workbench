from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]

MIN_PRODUCTION_SECRET_LENGTH = 32


def _secret_weak_reason(value: str, blocked_values: set[str]) -> str | None:
    """返回生产密钥不合规原因，合规则返回 None。"""
    stripped = value.strip()
    if stripped in blocked_values or stripped.startswith("replace-with-"):
        return "不能使用默认值或示例占位符"
    if len(stripped) < MIN_PRODUCTION_SECRET_LENGTH:
        return f"长度至少 {MIN_PRODUCTION_SECRET_LENGTH} 个字符"
    if len(set(stripped)) <= 2:
        return "不能使用过于简单的重复字符"
    return None


class Settings(BaseSettings):
    """应用运行配置。

    配置优先从环境变量和 `.env` 文件读取；生产环境必须覆盖默认密钥。
    """

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"),
        extra="ignore",
    )

    APP_NAME: str = "zhike-workshop"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://zhike:zhike_password@localhost:5432/zhike_workshop"
    VALKEY_URL: str = "redis://localhost:6379/0"
    OBJECT_STORAGE_ROOT: str = "./storage"
    MODEL_PROVIDER_ICONS_DIR: str = "./storage/provider-icons"
    SITE_ASSETS_DIR: str = "./storage/site-assets"
    MAX_DOCUMENT_UPLOAD_BYTES: int = 50 * 1024 * 1024
    AUTH_BACKGROUND_MAX_BYTES: int = 40 * 1024 * 1024
    ALLOWED_DOCUMENT_EXTENSIONS: str = ".pdf,.md,.markdown,.txt,.text"
    ALLOWED_DOCUMENT_MIME_TYPES: str = "application/pdf,text/markdown,text/plain,application/octet-stream"
    # 同课程相同 content_hash 时拒绝上传（管理员可 force_reupload 绕过）
    BLOCK_DUPLICATE_DOCUMENT_UPLOAD: bool = True
    # 同课程相同显示名/文件名时拒绝上传（与列表「文档名」一致，大小写不敏感）
    BLOCK_DUPLICATE_FILENAME: bool = True

    JWT_SECRET_KEY: str = "change-me"
    ENCRYPTION_KEY: str = "change-me-32-bytes-key"
    DEV_AUTH_SKIP_PASSWORD_CHECK: bool = False

    DEFAULT_COURSE_ID: str = "deep_learning_001"
    DEFAULT_MODEL_PROVIDER: str = "deepseek"
    DEFAULT_CHAT_MODEL: str = "deepseek-chat"
    DEFAULT_EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 384
    # 本地知识库配置；缓存目录通过环境变量覆盖，避免把模型权重提交到仓库。
    LOCAL_EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    LOCAL_EMBEDDING_DIMENSION: int = 512
    LOCAL_EMBEDDING_CACHE_DIR: str = "./storage/models"
    LOCAL_EMBEDDING_DEVICE: str = "cpu"
    LOCAL_KNOWLEDGE_CHUNK_SIZE: int = 1200
    LOCAL_KNOWLEDGE_CHUNK_OVERLAP: int = 150
    # 分块器版本标识，用于追踪切片来源；"page-paragraph-v1" 为旧版字符级，"sentence-window-v2" 为句子级滑动窗口
    LOCAL_KNOWLEDGE_CHUNKER_VERSION: str = "sentence-window-v2"
    LOCAL_KNOWLEDGE_BM25_WEIGHT: float = 0.3
    LOCAL_KNOWLEDGE_VECTOR_WEIGHT: float = 0.7
    LOCAL_KNOWLEDGE_SNIPPET_SIZE: int = 800
    RAG_RETRIEVAL_LIMIT: int = 5
    RAG_RETRIEVAL_MIN_SCORE: float = 0.65
    RAG_BACKEND: str = "iflytek_chatdoc"
    # 知识库凭证环境变量名由 rag_integration_templates.json 的 env_prefix + 字段 key 动态组成
    # true 表示上传在云端切分后等待管理员激活向量化；false 表示上传后自动向量化。
    CHATDOC_STEP_BY_STEP: bool = True
    # ChatDoc 回调使用的公网 API 根地址，例如 https://api.example.com。
    PUBLIC_API_BASE_URL: str = "http://localhost:8001"
    CHATDOC_WEBHOOK_PATH: str = "/api/v1/webhooks/chatdoc/status"
    CHATDOC_WEBHOOK_VERIFY_SIGNATURE: bool = False
    MODEL_GATEWAY_BASE_URL: str = "https://api.deepseek.com"
    MODEL_GATEWAY_TIMEOUT_SECONDS: float = 60.0
    MODEL_GATEWAY_MAX_TOKENS: int = 1200
    MODEL_GATEWAY_TEMPERATURE: float = 0.2
    MODEL_GATEWAY_CACHE_TTL_SECONDS: int = 30
    MODEL_GATEWAY_RELOAD_CHANNEL: str = "model_gateway.config_reload"
    RESOURCE_TASK_PROGRESS_CHANNEL_PREFIX: str = "resource.task.progress:"
    CHAT_RATE_LIMIT_PER_MINUTE: int = 30
    RESOURCE_TASK_DAILY_LIMIT: int = 50
    RESOURCE_REFERENCE_IMAGE_MAX_BYTES: int = 8 * 1024 * 1024
    RESOURCE_REFERENCE_IMAGE_MAX_COUNT: int = 6
    RESOURCE_IMAGE_GENERATION_TIMEOUT_SECONDS: float = 120.0
    RESOURCE_IMAGE_GENERATION_POLL_INTERVAL_SECONDS: float = 2.0
    RESOURCE_IMAGE_GENERATION_POLL_ATTEMPTS: int = 60
    MODEL_GATEWAY_FAILURE_THRESHOLD: int = 3
    MODEL_GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS: int = 600
    MODEL_GATEWAY_HEALTH_COOLDOWN_SECONDS: int = 300

    # 代码沙箱：后端转发到 Node + Pyodide 微服务执行用户代码
    SANDBOX_SERVICE_URL: str = "http://127.0.0.1:8003"
    SANDBOX_EXECUTION_TIMEOUT_SECONDS: float = 10.0
    SANDBOX_MAX_CODE_BYTES: int = 64 * 1024
    SANDBOX_RATE_LIMIT_PER_MINUTE: int = 20

    # 文档解析/向量化由讯飞 ChatDoc 云端完成（PDF / TXT / MD）
    RESOURCE_GENERATION_WORKER_ENABLED: bool = True
    RESOURCE_GENERATION_POLL_INTERVAL_SECONDS: float = 2.0
    PROFILE_LLM_EXTRACTION_ENABLED: bool = True
    ASSESSMENT_LLM_RUBRIC_ENABLED: bool = True
    ASSESSMENT_LLM_CONCURRENCY: int = 5
    INTENT_ROUTER_REGISTRY_PATH: str = ""
    INTENT_ROUTER_EMBEDDING_ENABLED: bool = True
    INTENT_ROUTER_LOW_CONFIDENCE_CLARIFY: bool = True
    INTENT_ROUTER_LLM_JUDGE_ENABLED: bool = True

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4174,http://127.0.0.1:4174"

    @cached_property
    def cors_origins_list(self) -> list[str]:
        """解析允许跨域访问的前端来源列表。"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @cached_property
    def allowed_document_extensions_set(self) -> set[str]:
        """解析允许上传的文档扩展名集合。"""
        return {item.strip().lower() for item in self.ALLOWED_DOCUMENT_EXTENSIONS.split(",") if item.strip()}

    @cached_property
    def allowed_document_mime_types_set(self) -> set[str]:
        """解析允许上传的文档 MIME 类型集合。"""
        return {item.strip().lower() for item in self.ALLOWED_DOCUMENT_MIME_TYPES.split(",") if item.strip()}

    @cached_property
    def is_production(self) -> bool:
        """判断当前是否为生产或预发布环境。"""
        return self.ENVIRONMENT.strip().lower() in {"production", "prod", "staging", "stage"}

    @cached_property
    def auth_skip_password_check_enabled(self) -> bool:
        """判断是否启用开发环境免密码登录。"""
        return self.DEV_AUTH_SKIP_PASSWORD_CHECK and not self.is_production

    def validate_runtime_security(self) -> None:
        """校验运行时安全配置。

        生产或预发布环境必须通过环境变量提供高强度密钥，不能沿用示例值或过短密钥。
        开发免密码登录只能在本地开发环境启用，避免演示配置误入预发布或生产。

        异常:
            RuntimeError: 生产环境密钥不满足强度要求时抛出。
        """
        if not self.is_production:
            return
        if self.DEV_AUTH_SKIP_PASSWORD_CHECK:
            raise RuntimeError("DEV_AUTH_SKIP_PASSWORD_CHECK 只能在 development 环境启用，生产或预发布环境必须关闭")
        insecure_values = {
            "JWT_SECRET_KEY": {
                "change-me",
                "change-me-in-production",
                "replace-with-random-64-char-secret",
            },
            "ENCRYPTION_KEY": {
                "change-me",
                "change-me-32-bytes-key",
                "replace-with-random-64-char-encryption-key",
            },
        }
        offenders = [
            f"{name}（{reason}）"
            for name, blocked_values in insecure_values.items()
            if (reason := _secret_weak_reason(getattr(self, name), blocked_values))
        ]
        if offenders:
            joined = ", ".join(offenders)
            raise RuntimeError(f"生产环境必须通过环境变量配置高强度安全密钥：{joined}")


settings = Settings()
