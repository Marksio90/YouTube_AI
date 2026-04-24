from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Broker / Backend ─────────────────────────────────────────────────────
    celery_broker_url: str
    celery_result_backend: str
    redis_url: str

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 3

    # ── AI / LLM ─────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    llm_default_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.7

    # ── YouTube ───────────────────────────────────────────────────────────────
    youtube_client_id: str = ""
    youtube_client_secret: str = ""

    # ── Storage (S3) ──────────────────────────────────────────────────────────
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_media: str = "ai-media-os-media"
    s3_region: str = "us-east-1"

    # ── Idempotency ────────────────────────────────────────────────────────────
    idempotency_default_ttl: int = 86_400    # 24 h
    idempotency_ai_ttl: int = 3_600          # 1 h — re-run AI if needed
    idempotency_analytics_ttl: int = 43_200  # 12 h per date

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = ""  # used for token decryption (same as backend)
    mock_media_base_url: str = "https://mock-media.local"


settings = WorkerSettings()
