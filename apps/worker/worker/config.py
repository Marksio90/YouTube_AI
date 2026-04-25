from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

from worker.llm_support import (
    SUPPORTED_PROVIDERS,
    is_model_supported,
    is_provider_supported,
    matrix_as_text,
    normalize_provider_name,
)


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
    elevenlabs_api_key: str = ""
    tts_provider_default: str = "openai"  # "openai" | "elevenlabs"
    llm_default_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.7
    # Local LLM (Ollama / LM Studio — OpenAI-compatible endpoint)
    llm_local_base_url: str = "http://localhost:11434/v1"
    llm_local_model: str = "llama3.2"
    llm_provider: str = "openai"  # "openai" | "local" | "mock"

    @model_validator(mode="after")
    def validate_llm_provider_and_model(self) -> "WorkerSettings":
        provider = normalize_provider_name(self.llm_provider)
        model = self.llm_default_model.strip()

        if not is_provider_supported(provider):
            supported = ", ".join(SUPPORTED_PROVIDERS)
            raise ValueError(
                f"Unsupported LLM_PROVIDER='{self.llm_provider}'. "
                f"Supported providers: {supported}."
            )

        if not is_model_supported(provider, model):
            raise ValueError(
                "Unsupported LLM_DEFAULT_MODEL/LLM_PROVIDER combination: "
                f"provider='{provider}', model='{self.llm_default_model}'. "
                f"Supported matrix: {matrix_as_text()}."
            )

        self.llm_provider = provider
        self.llm_default_model = model
        return self

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
    secret_key: str
    mock_media_base_url: str = "https://mock-media.local"

    @model_validator(mode="after")
    def validate_secret_key(self) -> "WorkerSettings":
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return self


settings = WorkerSettings()
