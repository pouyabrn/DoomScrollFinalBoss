from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from finalboss.models import SourceRegistry

MAX_RECIPIENTS = 10


class NewsletterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    subtitle: str = Field(min_length=1, max_length=200)
    timezone: str
    locale: str = "en"
    top_n: int = Field(default=20, ge=1, le=20)
    lookback_hours: int = Field(default=40, ge=12, le=168)
    max_collected_items: int = Field(default=500, ge=20, le=2000)
    max_llm_candidates: int = Field(default=50, ge=10, le=100)
    min_story_score: float = Field(default=20.0, ge=0.0, le=100.0)
    max_items_per_source: int = Field(default=4, ge=1, le=20)
    max_items_per_category: int = Field(default=7, ge=1, le=20)


class LlmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=3, max_length=150)
    fallback_models: list[str] = Field(default_factory=list, max_length=3)
    max_output_tokens: int = Field(default=10000, ge=1000, le=32000)
    temperature: float = Field(default=0.15, ge=0.0, le=1.0)
    timeout_seconds: int = Field(default=90, ge=10, le=180)
    max_attempts: int = Field(default=3, ge=1, le=5)
    require_zero_data_retention: bool = False
    prompt_version: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")


class DeliveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["resend"] = "resend"
    subject_prefix: str = Field(min_length=1, max_length=80)
    tracking_enabled: bool = False
    max_force_resends_per_day: int = Field(default=3, ge=1, le=5)

    @field_validator("tracking_enabled")
    @classmethod
    def tracking_must_be_off(cls, value: bool) -> bool:
        if value:
            raise ValueError("private digest tracking must remain disabled")
        return value


class NetworkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concurrency: int = Field(default=12, ge=1, le=30)
    per_host_concurrency: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=18, ge=3, le=60)
    max_response_bytes: int = Field(default=3_000_000, ge=100_000, le=10_000_000)
    user_agent: str = Field(min_length=20, max_length=300)


class SocialConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reddit_subreddits: list[str] = Field(default_factory=list, max_length=30)
    reddit_items_per_listing: int = Field(default=25, ge=5, le=100)
    reddit_skip_self_posts: bool = True
    x_accounts: list[str] = Field(default_factory=list, max_length=40)
    x_max_posts_per_day: int = Field(default=10, ge=0, le=10)

    @field_validator("reddit_skip_self_posts")
    @classmethod
    def self_posts_must_be_skipped(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Reddit self-post ingestion is intentionally unsupported")
        return value


class PublicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    newsletter: NewsletterConfig
    llm: LlmConfig
    delivery: DeliveryConfig
    network: NetworkConfig
    social: SocialConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FINALBOSS_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: SecretStr = SecretStr("sqlite:///./.state/finalboss.db")
    openrouter_api_key: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    email_to: SecretStr | None = None
    email_from: SecretStr | None = None
    privacy_key: SecretStr | None = None
    healthcheck_url: SecretStr | None = None
    x_bearer_token: SecretStr | None = None
    reddit_client_id: SecretStr | None = None
    reddit_client_secret: SecretStr | None = None
    config_path: Path = Path("config/newsletter.yaml")
    sources_path: Path = Path("config/sources.yaml")
    log_level: str = "INFO"
    environment: Literal["development", "test", "production"] = "development"

    @model_validator(mode="after")
    def production_requires_persistent_database(self) -> Settings:
        if self.environment == "production" and self.database_url.get_secret_value().startswith(
            "sqlite:"
        ):
            raise ValueError("production requires persistent Postgres via FINALBOSS_DATABASE_URL")
        return self


def _read_yaml(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except OSError as exc:
        raise ValueError(f"cannot read configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML configuration: {path}") from exc


def load_configuration(settings: Settings) -> tuple[PublicConfig, SourceRegistry]:
    public = PublicConfig.model_validate(_read_yaml(settings.config_path))
    sources = SourceRegistry.model_validate(_read_yaml(settings.sources_path))
    return public, sources


def secret_value(secret: SecretStr | None) -> str | None:
    return secret.get_secret_value() if secret is not None else None


def parse_recipient_emails(secret: SecretStr | None) -> tuple[str, ...]:
    value = secret_value(secret)
    if not value:
        return ()
    candidates = [item.strip() for item in re.split(r"[,;\n]+", value) if item.strip()]

    recipients: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            normalized = validate_email(candidate, check_deliverability=False).normalized
        except EmailNotValidError:
            raise ValueError("recipient list contains an invalid email address") from None
        identity = normalized.casefold()
        if identity not in seen:
            seen.add(identity)
            recipients.append(normalized)
    if len(recipients) > MAX_RECIPIENTS:
        raise ValueError(f"at most {MAX_RECIPIENTS} newsletter recipients are allowed")
    return tuple(recipients)
