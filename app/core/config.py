from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_name: str = "Metrics Receiver"
    environment: str = "production"
    secret_key: str = "CHANGE_ME"

    # DB
    database_url: str = "postgresql+asyncpg://metrics:metrics@db:5432/metrics"

    # Bootstrap admin
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "admin123!"

    # Alerting defaults (can be overridden in UI settings table)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    # Heartbeat / worker
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 30


settings = Settings()
