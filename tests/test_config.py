from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from finalboss.config import MAX_RECIPIENTS, Settings, load_configuration, parse_recipient_emails
from finalboss.models import FeedDefinition, SitemapDefinition, SourceRegistry


def test_public_configuration_loads() -> None:
    settings = Settings(
        config_path=Path("config/newsletter.yaml"),
        sources_path=Path("config/sources.yaml"),
    )
    public, registry = load_configuration(settings)
    assert public.newsletter.top_n == 20
    assert public.delivery.tracking_enabled is False
    assert len(registry.feeds) >= 25
    assert len(registry.sitemaps) == 4
    assert any(feed.id == "openrouter-models" for feed in registry.feeds)


def test_feed_requires_https() -> None:
    with pytest.raises(ValidationError):
        FeedDefinition.model_validate(
            {
                "id": "bad-feed",
                "name": "Bad",
                "url": "http://example.com/feed",
                "category": "press",
                "tier": "press",
                "weight": 0.5,
                "max_items": 10,
                "terms_note": "Fixture",
            }
        )


def test_production_rejects_ephemeral_sqlite() -> None:
    with pytest.raises(ValidationError, match="persistent Postgres"):
        Settings(environment="production", database_url="sqlite:///temporary.db")


def test_source_ids_are_globally_unique() -> None:
    feed = FeedDefinition(
        id="duplicate-source",
        name="Feed",
        url="https://example.com/feed",
        category="labs",
        tier="primary",
        weight=1,
        terms_note="Fixture.",
    )
    sitemap = SitemapDefinition(
        id="duplicate-source",
        name="Sitemap",
        url="https://example.com/sitemap.xml",
        include_pattern="/news/",
        category="labs",
        tier="primary",
        weight=1,
        terms_note="Fixture.",
    )
    with pytest.raises(ValidationError, match="globally unique"):
        SourceRegistry(feeds=[feed], sitemaps=[sitemap])


def test_recipient_list_normalizes_and_deduplicates_private_addresses() -> None:
    recipients = parse_recipient_emails(
        SecretStr("Owner@EXAMPLE.com,\r\nfriend@example.com; owner@example.com\nthird@example.com")
    )
    assert recipients == (
        "Owner@example.com",
        "friend@example.com",
        "third@example.com",
    )


def test_recipient_limit_applies_after_deduplication() -> None:
    repeated = ["owner@example.com"] * (MAX_RECIPIENTS + 1)
    assert parse_recipient_emails(SecretStr(",".join(repeated))) == ("owner@example.com",)

    unique = [f"person-{index}@example.com" for index in range(MAX_RECIPIENTS + 1)]
    with pytest.raises(ValueError, match=f"at most {MAX_RECIPIENTS}"):
        parse_recipient_emails(SecretStr("\n".join(unique)))


def test_invalid_recipient_error_does_not_expose_the_value() -> None:
    private_value = "private-person-at-example.com"
    with pytest.raises(ValueError, match="invalid email") as captured:
        parse_recipient_emails(SecretStr(private_value))
    assert private_value not in str(captured.value)
    assert captured.value.__cause__ is None
