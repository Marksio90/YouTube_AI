from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    celery_broker_url: str
    celery_result_backend: str
    redis_url: str
    database_url: str
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_default_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.7
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_media: str = "ai-media-os-media"
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    log_level: str = "INFO"


settings = WorkerSettings()
