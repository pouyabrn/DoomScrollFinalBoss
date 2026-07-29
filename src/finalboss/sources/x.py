from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from finalboss.config import Settings, SocialConfig, secret_value
from finalboss.http import BoundedHttpClient
from finalboss.models import (
    CollectionResult,
    SourceKind,
    SourceStatus,
    Story,
    TrustTier,
)
from finalboss.processing.normalize import canonicalize_url, clean_text, story_id

_USERNAME = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class XAdapter:
    SEARCH_URL = "https://api.x.com/2/tweets/search/recent"

    def __init__(
        self,
        config: SocialConfig,
        settings: Settings,
        client: BoundedHttpClient,
    ) -> None:
        self._config = config
        self._settings = settings
        self._client = client

    async def collect(self, *, since: datetime) -> CollectionResult:
        started = time.monotonic()
        token = secret_value(self._settings.x_bearer_token)
        if not token or self._config.x_max_posts_per_day == 0:
            return CollectionResult(
                statuses=[
                    SourceStatus(
                        source_id="x",
                        source_kind=SourceKind.X,
                        ok=False,
                        skipped=True,
                        error_code="credentials_missing",
                    )
                ]
            )
        try:
            accounts = [name for name in self._config.x_accounts if _USERNAME.fullmatch(name)]
            if not accounts:
                raise ValueError("no valid X accounts configured")
            account_query = " OR ".join(f"from:{name}" for name in accounts)
            query = f"({account_query}) -is:retweet -is:reply lang:en"
            if len(query) > 512:
                raise ValueError("configured X query exceeds 512 characters")
            payload = await self._client.get_json(
                self.SEARCH_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "query": query,
                    "max_results": self._config.x_max_posts_per_day,
                    "tweet.fields": "author_id,created_at,entities,public_metrics",
                    "expansions": "author_id",
                    "user.fields": "username",
                    "sort_order": "relevancy",
                    "start_time": since.isoformat().replace("+00:00", "Z"),
                },
            )
            users = {
                str(user.get("id")): str(user.get("username") or "unknown")
                for user in payload.get("includes", {}).get("users", [])
            }
            stories = [
                story
                for item in payload.get("data", [])
                if (story := self._story(item, users=users)) is not None
            ]
            return CollectionResult(
                stories=stories,
                statuses=[
                    SourceStatus(
                        source_id="x",
                        source_kind=SourceKind.X,
                        ok=True,
                        item_count=len(stories),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
                ],
            )
        except Exception as exc:
            return CollectionResult(
                statuses=[
                    SourceStatus(
                        source_id="x",
                        source_kind=SourceKind.X,
                        ok=False,
                        error_code=type(exc).__name__,
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
                ]
            )

    @staticmethod
    def _story(item: dict[str, Any], *, users: dict[str, str]) -> Story | None:
        post_id = str(item.get("id") or "")
        username = users.get(str(item.get("author_id")), "unknown")
        entities = item.get("entities") or {}
        urls = entities.get("urls") or []
        target: str | None = None
        for candidate in urls:
            expanded = str(candidate.get("unwound_url") or candidate.get("expanded_url") or "")
            host = (urlsplit(expanded).hostname or "").lower()
            if expanded.startswith("https://") and not host.endswith(("x.com", "twitter.com")):
                target = expanded
                break
        if not post_id or not target:
            return None
        try:
            canonical = canonicalize_url(target)
        except ValueError:
            return None
        published = datetime.fromisoformat(str(item["created_at"]).replace("Z", "+00:00"))
        metrics = item.get("public_metrics") or {}
        discussion = f"https://x.com/{username}/status/{post_id}"
        return Story(
            id=story_id("x", post_id),
            external_id=post_id,
            source_id="x",
            source_name=f"X / @{username}",
            source_kind=SourceKind.X,
            trust_tier=TrustTier.SOCIAL,
            source_weight=0.50,
            category="social",
            title=clean_text(str(item.get("text") or "X signal"), limit=500),
            url=canonical,
            canonical_url=canonical,
            discussion_url=discussion,
            published_at=published.astimezone(UTC),
            discovered_at=datetime.now(UTC),
            metrics={
                "likes": max(0, int(metrics.get("like_count") or 0)),
                "reposts": max(0, int(metrics.get("retweet_count") or 0)),
                "replies": max(0, int(metrics.get("reply_count") or 0)),
            },
            social_only=True,
        )
