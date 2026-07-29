from __future__ import annotations

import asyncio
import calendar
import time
from datetime import UTC, datetime
from typing import Any

import feedparser

from finalboss.http import BoundedHttpClient
from finalboss.models import (
    CollectionResult,
    FeedDefinition,
    SourceKind,
    SourceRegistry,
    SourceStatus,
    Story,
)
from finalboss.processing.normalize import canonicalize_url, clean_text, story_id


class FeedAdapter:
    def __init__(self, registry: SourceRegistry, client: BoundedHttpClient) -> None:
        self._registry = registry
        self._client = client

    async def collect(self, *, since: datetime) -> CollectionResult:
        tasks = [
            self._collect_feed(feed, since=since) for feed in self._registry.feeds if feed.enabled
        ]
        results = await asyncio.gather(*tasks)
        stories = [story for result, _ in results for story in result]
        statuses = [status for _, status in results]
        return CollectionResult(stories=stories, statuses=statuses)

    async def _collect_feed(
        self, feed: FeedDefinition, *, since: datetime
    ) -> tuple[list[Story], SourceStatus]:
        started = time.monotonic()
        try:
            body, _, _ = await self._client.request_bytes("GET", str(feed.url))
            parsed: Any = feedparser.parse(body)
            if parsed.get("bozo") and not parsed.get("entries"):
                raise ValueError("malformed feed")
            stories: list[Story] = []
            for entry in parsed.get("entries", [])[: feed.max_items]:
                story = self._story_from_entry(feed, entry)
                if story is not None and story.published_at >= since:
                    stories.append(story)
            status = SourceStatus(
                source_id=feed.id,
                source_kind=SourceKind.RSS,
                ok=True,
                item_count=len(stories),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            return stories, status
        except Exception as exc:
            status = SourceStatus(
                source_id=feed.id,
                source_kind=SourceKind.RSS,
                ok=False,
                error_code=type(exc).__name__,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            return [], status

    def _story_from_entry(self, feed: FeedDefinition, entry: Any) -> Story | None:
        link = str(entry.get("link") or "").strip()
        title = clean_text(str(entry.get("title") or ""), limit=500)
        if not link or not title:
            return None
        try:
            canonical = canonicalize_url(link)
        except ValueError:
            return None
        external_id = str(entry.get("id") or entry.get("guid") or canonical)
        published = self._entry_datetime(entry)
        summary = str(entry.get("summary") or entry.get("description") or "")
        content = entry.get("content") or []
        if content and isinstance(content, list) and isinstance(content[0], dict):
            summary = str(content[0].get("value") or summary)
        return Story(
            id=story_id(feed.id, external_id),
            external_id=external_id[:500],
            source_id=feed.id,
            source_name=feed.name,
            source_kind=SourceKind.RSS,
            trust_tier=feed.tier,
            source_weight=feed.weight,
            category=feed.category,
            title=title,
            url=canonical,
            canonical_url=canonical,
            excerpt=clean_text(summary, limit=4000),
            published_at=published,
            discovered_at=datetime.now(UTC),
        )

    @staticmethod
    def _entry_datetime(entry: Any) -> datetime:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
        return datetime.now(UTC)
