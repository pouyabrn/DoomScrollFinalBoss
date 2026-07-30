from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class SourceKind(StrEnum):
    RSS = "rss"
    SITEMAP = "sitemap"
    REDDIT = "reddit"
    X = "x"


class TrustTier(StrEnum):
    PRIMARY = "primary"
    RESEARCH = "research"
    EXPERT = "expert"
    PRESS = "press"
    SOCIAL = "social"


class FeedDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    category: str = Field(min_length=1, max_length=40)
    tier: TrustTier
    weight: float = Field(ge=0.0, le=1.0)
    max_items: int = Field(default=15, ge=1, le=100)
    enabled: bool = True
    terms_note: str = Field(min_length=1, max_length=300)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("feed URLs must use HTTPS")
        return value


class SitemapDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    include_pattern: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=40)
    tier: TrustTier
    weight: float = Field(ge=0.0, le=1.0)
    max_items: int = Field(default=10, ge=1, le=30)
    max_child_sitemaps: int = Field(default=8, ge=1, le=20)
    enabled: bool = True
    terms_note: str = Field(min_length=1, max_length=300)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("sitemap URLs must use HTTPS")
        return value


class SourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feeds: list[FeedDefinition]
    sitemaps: list[SitemapDefinition] = Field(default_factory=list)

    @field_validator("feeds", "sitemaps")
    @classmethod
    def unique_ids(
        cls, value: list[FeedDefinition] | list[SitemapDefinition]
    ) -> list[FeedDefinition] | list[SitemapDefinition]:
        ids = [source.id for source in value]
        if len(ids) != len(set(ids)):
            raise ValueError("source IDs must be unique")
        return value

    @model_validator(mode="after")
    def globally_unique_ids(self) -> SourceRegistry:
        ids = [source.id for source in self.feeds] + [source.id for source in self.sitemaps]
        if len(ids) != len(set(ids)):
            raise ValueError("source IDs must be globally unique")
        return self


class Story(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    external_id: str
    source_id: str
    source_name: str
    source_kind: SourceKind
    trust_tier: TrustTier
    source_weight: float = Field(ge=0.0, le=1.0)
    category: str
    title: str = Field(min_length=1, max_length=500)
    url: str
    canonical_url: str
    discussion_url: str | None = None
    excerpt: str = Field(default="", max_length=4000)
    published_at: datetime
    discovered_at: datetime
    metrics: dict[str, int] = Field(default_factory=dict)
    corroborating_sources: list[str] = Field(default_factory=list)
    social_only: bool = False
    deterministic_score: float = 0.0
    cluster_size: int = 1


class SourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_kind: SourceKind
    ok: bool
    skipped: bool = False
    item_count: int = 0
    error_code: str | None = None
    elapsed_ms: int = 0


class CollectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stories: list[Story] = Field(default_factory=list)
    statuses: list[SourceStatus] = Field(default_factory=list)


class EditorialItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    importance: int = Field(ge=0, le=100)
    eli5: str = Field(min_length=10, max_length=500)
    why_it_matters: str = Field(min_length=10, max_length=300)
    category: str = Field(min_length=2, max_length=40)
    confidence: Literal["low", "medium", "high"]
    uncertainty: str = Field(default="", max_length=180)

    @field_validator("eli5", "why_it_matters", "uncertainty")
    @classmethod
    def one_line(cls, value: str) -> str:
        return " ".join(value.split())


class LinkedInDraft(BaseModel):
    """Bounded, grounded prose returned by the editorial model."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=10, max_length=160)
    post_lines: list[str] = Field(min_length=4, max_length=7)
    why_now: str = Field(min_length=10, max_length=300)
    evidence_item_ids: list[str] = Field(min_length=1, max_length=3)

    @field_validator("topic", "why_now")
    @classmethod
    def one_line(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("post_lines")
    @classmethod
    def compact_post(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(line.split()) for line in value]
        if any(len(line) < 10 or len(line) > 420 for line in normalized):
            raise ValueError("LinkedIn post lines must each contain 10-420 characters")
        if sum(len(line) for line in normalized) > 1800:
            raise ValueError("LinkedIn post must not exceed 1,800 characters")
        return normalized

    @field_validator("evidence_item_ids")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("LinkedIn evidence item IDs must be unique")
        return value


class EditorialResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EditorialItem]
    forecast_lines: list[str] = Field(min_length=2, max_length=3)
    forecast_confidence: Literal["low", "medium", "high"]
    evidence_item_ids: list[str] = Field(min_length=1, max_length=8)

    @field_validator("forecast_lines")
    @classmethod
    def compact_forecast(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(line.split()) for line in value]
        if any(len(line) < 10 or len(line) > 240 for line in normalized):
            raise ValueError("forecast lines must each contain 10-240 characters")
        return normalized


class DigestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1, le=20)
    story: Story
    editorial: EditorialItem
    final_score: float = Field(ge=0.0, le=100.0)


class LinkedInOpportunity(BaseModel):
    """Rendered recommendation with application-computed, bounded scores."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=10, max_length=160)
    post_lines: list[str] = Field(min_length=4, max_length=7)
    why_now: str = Field(min_length=10, max_length=300)
    impression_potential: int = Field(ge=0, le=90)
    model_confidence: int = Field(ge=0, le=65)
    evidence_item_ids: list[str] = Field(min_length=1, max_length=3)
    signal_basis: Literal["daily-news-only"] = "daily-news-only"


class Digest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edition_date: date
    generated_at: datetime
    title: str
    subtitle: str
    items: list[DigestItem] = Field(max_length=20)
    forecast_lines: list[str] = Field(min_length=2, max_length=3)
    forecast_confidence: Literal["low", "medium", "high"]
    linkedin_opportunity: LinkedInOpportunity
    source_statuses: list[SourceStatus]
    model: str
    prompt_version: str


class RenderedDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    html: str
    text: str


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    edition_date: date
    collected_count: int
    clustered_count: int
    candidate_count: int
    digest_count: int
    sent: bool
    degraded_sources: int
    output_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
