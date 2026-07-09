import json
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_listish_setting(value: object) -> object:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            return json.loads(raw)
        return [item.strip() for item in raw.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    app_name: str = "Pixpress1 API"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/pixpress1"
    test_database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/pixpress1_test"
    redis_url: str = "redis://127.0.0.1:6379/0"
    queue_worker_concurrency: int = 4
    queue_job_timeout_seconds: int = 1800
    queue_enqueue_timeout_ms: int = 300
    queue_max_attempts: int = 3
    task_heartbeat_interval_seconds: int = 15
    task_stale_running_timeout_seconds: int = 600
    task_dispatch_batch_size: int = 100
    async_tasks_enabled: bool = True
    async_clean_enabled: bool = True
    async_cluster_enabled: bool = True
    async_plan_enabled: bool = True
    async_render_enabled: bool = True
    async_export_enabled: bool = True
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "pixpress1"
    minio_secure: bool = False
    minio_public_base_url: str | None = None
    uploads_dir: str = "uploads"
    auth_secret_key: str = "change-me-in-production"
    auth_algorithm: str = "HS256"
    auth_access_token_exp_minutes: int = 60 * 24
    cors_allow_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["Authorization", "Content-Type"])
    storage_backend: str = "local"
    upload_max_file_size_bytes: int = 20 * 1024 * 1024
    upload_max_batch_size_bytes: int = 200 * 1024 * 1024
    upload_max_image_pixels: int = 60_000_000
    upload_max_files_per_request: int = 200
    auth_login_max_failures: int = 5
    auth_login_lockout_seconds: int = 15 * 60
    auth_login_attempt_window_seconds: int = 15 * 60
    rate_limit_enabled: bool = True
    rate_limit_login: str = "5/minute"
    rate_limit_register: str = "10/hour"
    rate_limit_upload: str = "20/minute"
    rate_limit_task_trigger: str = "10/minute"
    rate_limit_export: str = "10/minute"
    ai_enabled: bool = False
    ai_provider_b1: str = ""
    ai_provider_b2: str = "openai_compatible"
    ai_provider_b3: str = "openai_compatible"
    ai_mode_b1: str = "hybrid"
    ai_mode_b2: str = "llm"
    ai_mode_b3: str = "llm"
    ai_fallback_on_error: bool = True
    llm_api_key: str | None = Field(default=None, validation_alias="API_KEY")
    llm_api_url: str | None = Field(default=None, validation_alias="API_URL")
    secrets_master_key: str | None = Field(default=None, validation_alias="SECRETS_MASTER_KEY")
    anthropic_api_key: str | None = None
    ai_model_b1: str = ""
    ai_model_b2: str = "gpt4-mini"
    ai_model_b3: str = "gpt4-mini"
    ai_request_timeout_seconds: int = 60
    ai_provider_max_retries: int = 2
    ai_b1_max_parallel: int = 3
    ai_image_max_edge: int = 1800
    ai_debug_persist: bool = True
    run_live_ai_tests: bool = False
    observability_log_level: str = "INFO"
    observability_json_logs: bool = True
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    sentry_traces_sample_rate: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def validate_cors_allow_origins(cls, value: object) -> object:
        return _parse_listish_setting(value)

    @field_validator("cors_allow_methods", "cors_allow_headers", mode="before")
    @classmethod
    def validate_string_list_fields(cls, value: object) -> object:
        return _parse_listish_setting(value)

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.upload_max_file_size_bytes <= 0:
            raise ValueError("UPLOAD_MAX_FILE_SIZE_BYTES must be positive")
        if self.upload_max_batch_size_bytes < self.upload_max_file_size_bytes:
            raise ValueError("UPLOAD_MAX_BATCH_SIZE_BYTES must be >= UPLOAD_MAX_FILE_SIZE_BYTES")
        if self.upload_max_image_pixels <= 0:
            raise ValueError("UPLOAD_MAX_IMAGE_PIXELS must be positive")
        if self.upload_max_files_per_request <= 0:
            raise ValueError("UPLOAD_MAX_FILES_PER_REQUEST must be positive")
        if self.auth_login_max_failures <= 0:
            raise ValueError("AUTH_LOGIN_MAX_FAILURES must be positive")
        if self.auth_login_lockout_seconds <= 0:
            raise ValueError("AUTH_LOGIN_LOCKOUT_SECONDS must be positive")
        if self.auth_login_attempt_window_seconds <= 0:
            raise ValueError("AUTH_LOGIN_ATTEMPT_WINDOW_SECONDS must be positive")

        if self.app_env.lower() != "production":
            return self
        if self.auth_secret_key == "change-me-in-production":
            raise ValueError("AUTH_SECRET_KEY must be set for production")
        if len(self.auth_secret_key) < 32:
            raise ValueError("AUTH_SECRET_KEY must be at least 32 characters in production")
        if not self.secrets_master_key or self.secrets_master_key == "change-me-too":
            raise ValueError("SECRETS_MASTER_KEY must be set for production")
        if len(self.secrets_master_key) < 32:
            raise ValueError("SECRETS_MASTER_KEY must be at least 32 characters in production")
        if self.auth_secret_key == self.secrets_master_key:
            raise ValueError("AUTH_SECRET_KEY and SECRETS_MASTER_KEY must be different")
        if not self.cors_allow_origins:
            raise ValueError("CORS_ALLOW_ORIGINS must be set for production")
        if any(not origin.strip() for origin in self.cors_allow_origins):
            raise ValueError("CORS_ALLOW_ORIGINS contains empty origin")
        if any(origin == "*" for origin in self.cors_allow_origins):
            raise ValueError("Wildcard CORS is not allowed in production")
        if any(not origin.startswith(("http://", "https://")) for origin in self.cors_allow_origins):
            raise ValueError("CORS_ALLOW_ORIGINS must contain full http/https origins")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def resolved_cors_allow_origins(self) -> list[str]:
        if self.cors_allow_origins:
            return self.cors_allow_origins
        if self.is_production:
            return []
        return [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
