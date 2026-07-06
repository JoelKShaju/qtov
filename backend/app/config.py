"""Application configuration loaded from environment / .env."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .agent.llm import OpenAIModel


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---
    openai_api_key: str = ""
    # OPENAI_MODEL is the single-model default used by BOTH agents (any OpenAIModel value or a
    # custom id; see app/agent/llm.py). Default gpt-4o-mini (broadly accessible).
    openai_model: str = OpenAIModel.GPT_4O_MINI.value
    # Optional ORDERED fallback chains per agent role (CSV, first = primary). Left empty by default
    # so each falls back to `openai_model` — set one to override just that agent.
    classifier_models: str = ""
    summarizer_models: str = ""

    @property
    def classifier_model_list(self) -> list[str]:
        return _csv(self.classifier_models) or [self.openai_model]

    @property
    def summarizer_model_list(self) -> list[str]:
        return _csv(self.summarizer_models) or [self.openai_model]

    # --- Database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/qtov"

    @field_validator("database_url")
    @classmethod
    def _async_db_url(cls, v: str) -> str:
        """Coerce a plain Postgres URL to the asyncpg driver SQLAlchemy needs.

        Managed hosts (Render, Heroku, etc.) hand out `postgres://` or `postgresql://`; the
        async engine requires the `postgresql+asyncpg://` scheme. Also drop a `sslmode` query
        param, which asyncpg rejects (it's a libpq/psycopg option).
        """
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        if "sslmode=" in v:
            base, _, query = v.partition("?")
            kept = "&".join(p for p in query.split("&") if not p.startswith("sslmode="))
            v = f"{base}?{kept}" if kept else base
        return v

    # --- ClinicalTrials.gov API ---
    clinicaltrials_base_url: str = "https://clinicaltrials.gov/api/v2/studies"
    max_records: int = 1000  # safety cap on records pulled per query
    page_size: int = 200  # API max is 1000; keep payloads reasonable
    http_timeout: float = 30.0
    # Max concurrent upstream requests in a single query's count fan-out (top-N / comparison),
    # so a wide query can't hammer or get throttled by ClinicalTrials.gov.
    upstream_concurrency: int = 8
    # Bounded retry with exponential backoff for transient upstream failures (429/5xx/timeouts).
    upstream_max_retries: int = 3
    upstream_backoff_base: float = 0.5  # seconds; delay = base * 2**attempt, capped
    upstream_backoff_cap: float = 8.0

    # --- Cache ---
    cache_ttl_seconds: int = 86_400

    # --- Observability ---
    logfire_token: str = ""
    otel_exporter_otlp_endpoint: str = ""
    service_name: str = "qtov-backend"
    log_level: str = "INFO"
    log_json: bool = True

    # --- API ---
    cors_origins: str = "*"

    # --- Rate limiting (per-IP, in-memory; for a public demo's LLM budget) ---
    # Off by default so local/dev/tests are unaffected; enable in a hosted deployment.
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 10

    def apply_runtime_env(self) -> None:
        """Export keys that downstream SDKs read directly from the environment."""
        if self.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.openai_api_key


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.apply_runtime_env()
    return settings


settings = get_settings()
