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
    rate_limit_upload: str = "120/minute"
    rate_limit_task_trigger: str = "10/minute"
    rate_limit_export: str = "10/minute"
    ai_enabled: bool = False
    ai_provider_b1: str = ""
    ai_provider_b2: str = "openai_compatible"
    ai_provider_b3: str = "openai_compatible"
    ai_chapter_provider: str | None = None
    ai_chapter_api_url: str | None = None
    ai_chapter_api_key: str | None = None
    ai_chapter_model: str | None = None
    ai_layout_provider: str | None = None
    ai_layout_api_url: str | None = None
    ai_layout_api_key: str | None = None
    ai_layout_model: str | None = None
    ai_chapter_embedding_provider: str | None = None
    ai_chapter_embedding_api_url: str | None = None
    ai_chapter_embedding_api_key: str | None = None
    ai_chapter_embedding_model: str | None = None
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
    cleaning_pipeline_version: str = "b2-local-v3"
    cleaning_analysis_max_parallel: int = 3
    cleaning_rollout_percent: int = 100
    cleaning_auto_exclude_mode: str = "exact_and_clear_quality"
    cleaning_hard_blur_mode: str = "shadow"
    cleaning_hard_blur_rollout_percent: int = 0
    cleaning_face_analysis_enabled: bool = True
    cleaning_face_max_parallel: int = 1
    cleaning_face_detector_model_path: str = "models/cleaning/blaze_face_full_range_sparse.tflite"
    cleaning_face_landmarker_model_path: str = "models/cleaning/face_landmarker.task"
    cleaning_anime_face_enabled: bool = True
    cleaning_anime_face_model_path: str = "models/cleaning/anime-face_yolov3.onnx"
    cleaning_pose_experiment_enabled: bool = False
    cleaning_pose_model_path: str = "models/cleaning/pose_landmarker_lite.task"
    theme_curation_enabled: bool = True
    theme_pipeline_version: str = "theme-curation-v7-embedding-only"
    theme_candidate_count: int = 3
    theme_relevance_calibration_path: str | None = None
    theme_provisional_auto_decision_enabled: bool = True
    theme_provisional_decision_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    chapter_representative_photo_count: int = 3
    chapter_naming_max_parallel: int = 2
    chapter_feature_version: str = "c4-image-embedding-only-v1"
    chapter_embedding_provider: str = "dashscope_multimodal_embedding"
    chapter_embedding_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
    chapter_embedding_api_key: str | None = None
    chapter_embedding_model: str = "qwen3-vl-embedding"
    chapter_embedding_dimension: int = 512
    chapter_embedding_batch_size: int = 8
    observability_log_level: str = "INFO"
    observability_json_logs: bool = True
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    sentry_traces_sample_rate: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
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
        if self.cleaning_analysis_max_parallel <= 0:
            raise ValueError("CLEANING_ANALYSIS_MAX_PARALLEL must be positive")
        if not 0 <= self.cleaning_rollout_percent <= 100:
            raise ValueError("CLEANING_ROLLOUT_PERCENT must be between 0 and 100")
        if self.cleaning_auto_exclude_mode not in {"off", "exact_only", "exact_and_clear_quality"}:
            raise ValueError("CLEANING_AUTO_EXCLUDE_MODE must be off, exact_only, or exact_and_clear_quality")
        if self.cleaning_hard_blur_mode not in {"shadow", "enforce"}:
            raise ValueError("CLEANING_HARD_BLUR_MODE must be shadow or enforce")
        if not 0 <= self.cleaning_hard_blur_rollout_percent <= 100:
            raise ValueError("CLEANING_HARD_BLUR_ROLLOUT_PERCENT must be between 0 and 100")
        if self.cleaning_face_max_parallel <= 0:
            raise ValueError("CLEANING_FACE_MAX_PARALLEL must be positive")
        if not 1 <= self.theme_candidate_count <= 5:
            raise ValueError("THEME_CANDIDATE_COUNT must be between 1 and 5")
        if not 1 <= self.chapter_representative_photo_count <= 3:
            raise ValueError("CHAPTER_REPRESENTATIVE_PHOTO_COUNT must be between 1 and 3")
        if self.chapter_naming_max_parallel <= 0:
            raise ValueError("CHAPTER_NAMING_MAX_PARALLEL must be positive")
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
    def resolved_chapter_config(self) -> tuple[str, str | None, str | None, str]:
        return (self.ai_chapter_provider or self.ai_provider_b2, self.ai_chapter_api_url or self.llm_api_url, self.ai_chapter_api_key or self.llm_api_key, self.ai_chapter_model or self.ai_model_b2)

    @property
    def resolved_layout_config(self) -> tuple[str, str | None, str | None, str]:
        return (self.ai_layout_provider or self.ai_provider_b3, self.ai_layout_api_url or self.llm_api_url, self.ai_layout_api_key or self.llm_api_key, self.ai_layout_model or self.ai_model_b3)

    @property
    def resolved_embedding_config(self) -> tuple[str, str | None, str | None, str]:
        return (self.ai_chapter_embedding_provider or self.chapter_embedding_provider, self.ai_chapter_embedding_api_url or self.chapter_embedding_api_url, self.ai_chapter_embedding_api_key or self.chapter_embedding_api_key or self.llm_api_key, self.ai_chapter_embedding_model or self.chapter_embedding_model)

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
