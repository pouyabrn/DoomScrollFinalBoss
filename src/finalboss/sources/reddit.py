from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

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


class RedditAdapter:
    AUTH_ENDPOINT = "https://www.reddit.com/api/v1/access_token"
    API_ROOT = "https://oauth.reddit.com"

    def __init__(
        self,
        config: SocialConfig,
        settings: Settings,
        client: BoundedHttpClient,
        *,
        user_agent: str,
    ) -> None:
        self._config = config
        self._settings = settings
        self._client = client
        self._user_agent = user_agent

    async def collect(self, *, since: datetime) -> CollectionResult:
        started = time.monotonic()
        client_id = secret_value(self._settings.reddit_client_id)
        client_secret = secret_value(self._settings.reddit_client_secret)
        if not client_id or not client_secret:
            return CollectionResult(
                statuses=[
                    SourceStatus(
                        source_id="reddit",
                        source_kind=SourceKind.REDDIT,
                        ok=False,
                        skipped=True,
                        error_code="credentials_missing",
                    )
                ]
            )
        try:
            token = await self._token(client_id, client_secret)
            stories: list[Story] = []
            for listing in ("new", "top"):
                stories.extend(await self._listing(listing, token=token, since=since))
            unique = {story.external_id: story for story in stories}
            return CollectionResult(
                stories=list(unique.values()),
                statuses=[
                    SourceStatus(
                        source_id="reddit",
                        source_kind=SourceKind.REDDIT,
                        ok=True,
                        item_count=len(unique),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
                ],
            )
        except Exception as exc:
            return CollectionResult(
                statuses=[
                    SourceStatus(
                        source_id="reddit",
                        source_kind=SourceKind.REDDIT,
                        ok=False,
                        error_code=type(exc).__name__,
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                    )
                ]
            )

    async def _token(self, client_id: str, client_secret: str) -> str:
        body, _, _ = await self._client.request_bytes(
            "POST",
            self.AUTH_ENDPOINT,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
            data={"grant_type": "client_credentials"},
            auth=httpx.BasicAuth(client_id, client_secret),
        )
        payload: Any = json.loads(body)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise ValueError("Reddit did not return an access token")
        return token

    async def _listing(self, listing: str, *, token: str, since: datetime) -> list[Story]:
        joined = "+".join(self._config.reddit_subreddits)
        params: dict[str, str | int] = {
            "limit": self._config.reddit_items_per_listing,
            "raw_json": 1,
        }
        if listing == "top":
            params["t"] = "day"
        payload = await self._client.get_json(
            f"{self.API_ROOT}/r/{joined}/{listing}",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": self._user_agent,
            },
            params=params,
        )
        children = payload.get("data", {}).get("children", [])
        stories: list[Story] = []
        for child in children:
            data = child.get("data", {}) if isinstance(child, dict) else {}
            story = self._story(data, since=since)
            if story is not None:
                stories.append(story)
        return stories

    def _story(self, data: dict[str, Any], *, since: datetime) -> Story | None:
        if data.get("is_self"):
            return None
        external_id = str(data.get("name") or data.get("id") or "")
        target = str(data.get("url_overridden_by_dest") or data.get("url") or "")
        if not external_id or not target:
            return None
        try:
            canonical = canonicalize_url(target)
        except ValueError:
            return None
        host = (urlsplit(canonical).hostname or "").lower()
        if host.endswith(("reddit.com", "redd.it")):
            return None
        published = datetime.fromtimestamp(float(data.get("created_utc", 0)), tz=UTC)
        if published < since:
            return None
        permalink = str(data.get("permalink") or "")
        discussion = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else None
        return Story(
            id=story_id("reddit", external_id),
            external_id=external_id,
            source_id="reddit",
            source_name="Reddit",
            source_kind=SourceKind.REDDIT,
            trust_tier=TrustTier.SOCIAL,
            source_weight=0.45,
            category="social",
            title=clean_text(str(data.get("title") or "Reddit signal"), limit=500),
            url=canonical,
            canonical_url=canonical,
            discussion_url=discussion,
            published_at=published,
            discovered_at=datetime.now(UTC),
            metrics={
                "score": max(0, int(data.get("score") or 0)),
                "comments": max(0, int(data.get("num_comments") or 0)),
            },
            social_only=True,
        )
