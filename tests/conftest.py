from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from finalboss.models import SourceKind, Story, TrustTier
from finalboss.processing.normalize import canonicalize_url, story_id


@pytest.fixture
def make_story() -> Callable[..., Story]:
    def factory(
        index: int = 1,
        *,
        source_id: str | None = None,
        source_kind: SourceKind = SourceKind.RSS,
        social_only: bool = False,
        url: str | None = None,
        title: str | None = None,
        excerpt: str | None = None,
        metrics: dict[str, int] | None = None,
    ) -> Story:
        actual_source = source_id or f"source-{index}"
        actual_url = url or f"https://example{index}.com/news/model-launch-{index}"
        canonical = canonicalize_url(actual_url)
        external_id = f"external-{actual_source}-{index}"
        return Story(
            id=story_id(actual_source, external_id),
            external_id=external_id,
            source_id=actual_source,
            source_name=f"Source {index}",
            source_kind=source_kind,
            trust_tier=TrustTier.SOCIAL if social_only else TrustTier.PRIMARY,
            source_weight=0.5 if social_only else 0.95,
            category="social" if social_only else f"category-{index % 5}",
            title=title or f"Lab {index} launches a major open source reasoning model",
            url=canonical,
            canonical_url=canonical,
            discussion_url=None,
            excerpt=excerpt
            or (
                f"The release {index} improves reasoning, lowers price, and includes "
                "a public technical report with benchmark details."
            ),
            published_at=datetime.now(UTC),
            discovered_at=datetime.now(UTC),
            metrics=metrics or {},
            social_only=social_only,
        )

    return factory
