"""Central configuration. Everything tunable lives here so nothing is hard-coded
across modules. Reads from environment variables (and a .env file in dev)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Storage and queue
    database_url: str = "postgresql+psycopg2://webhook:webhook@db:5432/webhook"
    redis_url: str = "redis://redis:6379/0"
    queue_key: str = "webhook:deliveries:due"

    # Delivery behaviour
    default_max_attempts: int = 6
    http_timeout_seconds: float = 8.0
    worker_poll_interval: float = 1.0
    worker_batch_size: int = 20

    # SSRF guard. Keep False in production. Set True only for local testing
    # against localhost receivers.
    allow_private_urls: bool = False


settings = Settings()
