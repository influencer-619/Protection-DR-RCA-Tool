"""Application configuration. Secrets must come from environment / secrets manager."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Protection RCA Platform"
    app_env: str = "development"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "change-me"
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8001,http://127.0.0.1:8001"
    )
    # Allow private-LAN origins when UI is opened via host IP (dev Vite or portable)
    cors_origin_regex: str = (
        r"https?://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?"
    )
    serve_frontend: bool = False
    frontend_dist: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    access_token_expire_minutes: int = 480

    database_url: str = (
        "postgresql+asyncpg://protection:protection_dev_only@localhost:5432/protection_rca"
    )

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "protection-rca"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    max_upload_size_mb: int = 200
    allowed_upload_extensions: str = ".cfg,.dat,.cff,.hdr,.inf,.csv,.txt,.xml,.json,.pdf,.zip"
    storage_backend: str = "auto"  # auto | s3 | local
    local_storage_path: str = "storage"
    rate_limit_per_minute: int = 600
    run_analysis_sync: bool = False  # True = sync in-process (dev/tests)

    auth_mode: str = "local"
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_audience: str = ""

    log_level: str = "INFO"
    enable_metrics: bool = True

    default_nominal_frequency: float = 50.0
    phasor_magnitude_tolerance: float = 0.02
    phase_angle_tolerance_deg: float = 1.0
    frequency_tolerance_hz: float = 0.05
    rms_tolerance: float = 0.02
    impedance_tolerance: float = 0.05
    timestamp_tolerance_us: int = 10

    # Algorithm / component versions (stored with every analysis)
    comtrade_parser_version: str = "1.0.0"
    signal_algorithm_version: str = "1.0.0"
    protection_rules_version: str = "1.0.0"
    consistency_rules_version: str = "1.0.0"
    rca_engine_version: str = "1.0.0"
    report_template_version: str = "1.0.0"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extensions(self) -> List[str]:
        return [
            e.strip().lower()
            for e in self.allowed_upload_extensions.split(",")
            if e.strip()
        ]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
