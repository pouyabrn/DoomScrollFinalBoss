from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlsplit

from defusedxml import ElementTree

from finalboss.http import BoundedHttpClient, validate_public_https_url
from finalboss.models import (
    CollectionResult,
    SitemapDefinition,
    SourceKind,
    SourceRegistry,
    SourceStatus,
    Story,
)
from finalboss.processing.normalize import canonicalize_url, clean_text, story_id


class SitemapAdapter:
    def __init__(self, registry: SourceRegistry, client: BoundedHttpClient) -> None:
        self._registry = registry
        self._client = client

    async def collect(self, *, since: datetime) -> CollectionResult:
        results = await asyncio.gather(
            *(
                self._collect_sitemap(definition, since=since)
                for definition in self._registry.sitemaps
                if definition.enabled
            )
        )
        return CollectionResult(
            stories=[story for stories, _ in results for story in stories],
            statuses=[status for _, status in results],
        )

    async def _collect_sitemap(
        self,
        definition: SitemapDefinition,
        *,
        since: datetime,
    ) -> tuple[list[Story], SourceStatus]:
        started = time.monotonic()
        try:
            root_host = _site_host(str(definition.url))
            urls = await self._read_tree(
                str(definition.url),
                root_host=root_host,
                child_budget=definition.max_child_sitemaps,
            )
            include = re.compile(definition.include_pattern, re.IGNORECASE)
            stories: list[Story] = []
            for location, modified in sorted(
                urls, key=lambda row: row[1] or datetime.min.replace(tzinfo=UTC), reverse=True
            ):
                if modified is None or modified < since or not include.search(location):
                    continue
                try:
                    canonical = canonicalize_url(location)
                except ValueError:
                    continue
                title = _title_from_url(canonical)
                if not title:
                    continue
                stories.append(
                    Story(
                        id=story_id(definition.id, canonical),
                        external_id=canonical,
                        source_id=definition.id,
                        source_name=definition.name,
                        source_kind=SourceKind.SITEMAP,
                        trust_tier=definition.tier,
                        source_weight=definition.weight,
                        category=definition.category,
                        title=title,
                        url=canonical,
                        canonical_url=canonical,
                        excerpt=(
                            "Official publisher page discovered in its sitemap; "
                            "no feed excerpt was provided."
                        ),
                        published_at=modified,
                        discovered_at=datetime.now(UTC),
                    )
                )
                if len(stories) >= definition.max_items:
                    break
            return stories, SourceStatus(
                source_id=definition.id,
                source_kind=SourceKind.SITEMAP,
                ok=True,
                item_count=len(stories),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            return [], SourceStatus(
                source_id=definition.id,
                source_kind=SourceKind.SITEMAP,
                ok=False,
                error_code=type(exc).__name__,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )

    async def _read_tree(
        self,
        url: str,
        *,
        root_host: str,
        child_budget: int,
    ) -> list[tuple[str, datetime | None]]:
        body, _, _ = await self._client.request_bytes("GET", url)
        root = ElementTree.fromstring(body)
        kind = _local_name(root.tag)
        if kind == "urlset":
            return _url_entries(root)
        if kind != "sitemapindex":
            raise ValueError("unsupported sitemap root element")
        child_urls = [
            (child.findtext("{*}loc") or "").strip()
            for child in root
            if _local_name(child.tag) == "sitemap"
        ][:child_budget]
        allowed = [
            child for child in child_urls if child and _same_site(child, root_host=root_host)
        ]
        nested = await asyncio.gather(
            *(self._read_tree(child, root_host=root_host, child_budget=0) for child in allowed)
        )
        return [entry for entries in nested for entry in entries]


def _url_entries(root: Any) -> list[tuple[str, datetime | None]]:
    entries: list[tuple[str, datetime | None]] = []
    for child in root:
        if _local_name(child.tag) != "url":
            continue
        location = (child.findtext("{*}loc") or "").strip()
        modified = _parse_datetime((child.findtext("{*}lastmod") or "").strip())
        if location:
            entries.append((location, modified))
    return entries


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _title_from_url(url: str) -> str:
    parts = [part for part in urlsplit(url).path.split("/") if part]
    if not parts:
        return ""
    slug = unquote(parts[-1]).removesuffix(".html")
    title = re.sub(r"[-_]+", " ", slug)
    return clean_text(title, limit=500).strip().title()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _site_host(url: str) -> str:
    validate_public_https_url(url)
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _same_site(url: str, *, root_host: str) -> bool:
    try:
        validate_public_https_url(url)
    except ValueError:
        return False
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return host == root_host or host.endswith(f".{root_host}")
