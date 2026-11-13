"""Application settings (12-factor: everything comes from the environment)."""

from __future__ import annotations

import hashlib
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-insecure-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXIOM_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./axiom.db"
    # Postgres row-level security (defense in depth on top of app-layer tenancy checks).
    enable_rls: bool = True

    secret_key: str = DEV_SECRET
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    storage_backend: str = "local"  # local | s3
    storage_path: str = "./storage"
    storage_encryption_key: str | None = None  # base64 32 bytes; derived from secret_key when unset
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    signed_url_seconds: int = 300
    max_upload_mb: int = 50

    # AI – the platform never depends on AI for numbers; these only enable
    # extraction proposals and narrative/explanations.
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"
    ai_enabled: bool = True  # still requires credentials (ANTHROPIC_API_KEY or profile)

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    billing_mode: str = "manual"  # manual (dev: owners switch plans directly) | stripe
    stripe_price_ids: dict[str, str] = Field(default_factory=dict)  # {"professional": "price_..."} (JSON env)

    seed_demo_on_register: bool = True
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    def encryption_key_bytes(self) -> bytes:
        if self.storage_encryption_key:
            import base64

            key = base64.b64decode(self.storage_encryption_key)
            if len(key) != 32:
                raise ValueError("AXIOM_STORAGE_ENCRYPTION_KEY must be 32 bytes, base64 encoded")
            return key
        return hashlib.sha256(f"{self.secret_key}:storage".encode()).digest()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.secret_key == DEV_SECRET:
        raise RuntimeError("AXIOM_SECRET_KEY must be set in production")
    return s
