"""Application settings (env-driven, with sane local defaults)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = 24 * 3600

    seed_demo: bool = True
    cors_origins: str = "http://localhost:8080,http://localhost:5173"

    # SMTP is emulated (outbox table) unless smtp_host is set.
    smtp_host: str | None = None
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "pulse@localhost"

    results_retention_days: int = 90
    scheduler_tick_seconds: float = 1.0
    demo_sites_url: str = "http://demo-sites:8090"
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
