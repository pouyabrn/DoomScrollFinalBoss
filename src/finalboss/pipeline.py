from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from finalboss.config import PublicConfig, Settings, secret_value
from finalboss.email.renderer import DigestRenderer
from finalboss.email.resend import ResendSender
from finalboss.http import BoundedHttpClient
from finalboss.llm.editor import (
    OpenRouterEditor,
    deterministic_editorial,
    ensure_editorial_coverage,
)
from finalboss.models import (
    CollectionResult,
    Digest,
    DigestItem,
    EditorialResult,
    RenderedDigest,
    RunSummary,
    SourceKind,
    SourceRegistry,
    SourceStatus,
    Story,
)
from finalboss.processing.dedupe import cluster_stories
from finalboss.processing.normalize import fingerprint
from finalboss.processing.rank import deterministic_rank, final_select
from finalboss.sources.base import SourceAdapter
from finalboss.sources.feeds import FeedAdapter
from finalboss.sources.reddit import RedditAdapter
from finalboss.sources.sitemaps import SitemapAdapter
from finalboss.sources.x import XAdapter
from finalboss.storage.database import Database, StoredDigest, recipient_fingerprint

logger = logging.getLogger(__name__)


class DigestPipeline:
    def __init__(
        self,
        settings: Settings,
        config: PublicConfig,
        registry: SourceRegistry,
    ) -> None:
        self._settings = settings
        self._config = config
        self._registry = registry

    async def run(
        self,
        *,
        send: bool,
        force_resend: bool = False,
        fixture: Path | None = None,
        output: Path | None = None,
    ) -> RunSummary:
        if force_resend and not send:
            raise ValueError("force resend requires delivery mode")
        now = datetime.now(UTC)
        timezone = ZoneInfo(self._config.newsletter.timezone)
        edition_date = now.astimezone(timezone).date()
        database_url = secret_value(self._settings.database_url)
        if database_url is None:
            raise RuntimeError("database URL is missing")
        database = Database(database_url)
        database.initialize(allow_create=self._settings.environment != "production")
        run_id = database.begin_run()
        collected_count = 0
        digest_count = 0
        degraded_sources = 0
        try:
            recipient, privacy_key = self._delivery_identity(required=send)
            recipient_hmac = (
                recipient_fingerprint(recipient, privacy_key)
                if recipient is not None and privacy_key is not None
                else "dry-run"
            )
            async with BoundedHttpClient(self._config.network) as client:
                if force_resend:
                    existing = database.get_digest(
                        edition_date=edition_date,
                        recipient_hmac=recipient_hmac,
                    )
                    if existing is None or existing.status != "sent":
                        raise RuntimeError(
                            "today's sent digest is unavailable; run a normal send first"
                        )
                    return await self._force_resend_existing(
                        existing=existing,
                        client=client,
                        database=database,
                        run_id=run_id,
                        recipient=recipient or "",
                        recipient_hmac=recipient_hmac,
                    )

                if send:
                    existing = database.get_digest(
                        edition_date=edition_date,
                        recipient_hmac=recipient_hmac,
                    )
                    if existing is not None:
                        if existing.status == "sent":
                            database.finish_run(
                                run_id,
                                status="already_sent",
                                collected_count=0,
                                digest_count=0,
                                degraded_sources=0,
                            )
                            return RunSummary(
                                run_id=run_id,
                                edition_date=edition_date,
                                collected_count=0,
                                clustered_count=0,
                                candidate_count=0,
                                digest_count=0,
                                sent=False,
                                degraded_sources=0,
                                metadata={"outcome": "already_sent"},
                            )
                        return await self._retry_existing(
                            existing=existing,
                            client=client,
                            database=database,
                            run_id=run_id,
                            recipient=recipient or "",
                            recipient_hmac=recipient_hmac,
                        )

                collection = (
                    self._load_fixture(fixture)
                    if fixture is not None
                    else await self._collect(
                        client, since=now - timedelta(hours=self._config.newsletter.lookback_hours)
                    )
                )
                collected = collection.stories[: self._config.newsletter.max_collected_items]
                collected_count = len(collected)
                degraded_sources = sum(
                    not status.ok and not status.skipped for status in collection.statuses
                )
                if fixture is None and sum(status.ok for status in collection.statuses) < 5:
                    raise RuntimeError("fewer than five source adapters were healthy")

                clustered = cluster_stories(collected)
                recent = database.recent_story_fingerprints(days=30)
                novel = [
                    story
                    for story in clustered
                    if fingerprint(story.canonical_url, story.title) not in recent
                ]
                ranked = deterministic_rank(novel, now=now)
                candidates = ranked[: self._config.newsletter.max_llm_candidates]
                if not candidates:
                    raise RuntimeError("no credible, unsent stories were collected")

                editorial, model_used = await self._edit(candidates, client=client)
                editorial = ensure_editorial_coverage(
                    editorial,
                    candidates,
                    top_n=self._config.newsletter.top_n,
                )
                selected = final_select(candidates, editorial.items, self._config.newsletter)
                if not selected:
                    raise RuntimeError("no stories passed the editorial threshold")

                digest = Digest(
                    edition_date=edition_date,
                    generated_at=now,
                    title=self._config.newsletter.title,
                    subtitle=self._config.newsletter.subtitle,
                    items=[
                        DigestItem(
                            position=index,
                            story=story,
                            editorial=item,
                            final_score=score,
                        )
                        for index, (story, item, score) in enumerate(selected, start=1)
                    ],
                    forecast_lines=editorial.forecast_lines,
                    forecast_confidence=editorial.forecast_confidence,
                    source_statuses=collection.statuses,
                    model=model_used,
                    prompt_version=self._config.llm.prompt_version,
                )
                rendered = DigestRenderer().render(
                    digest,
                    subject_prefix=self._config.delivery.subject_prefix,
                )
                digest_count = len(digest.items)

                if not send:
                    output_path = output or Path("preview") / f"digest-{edition_date}.html"
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(rendered.html, encoding="utf-8")
                    database.finish_run(
                        run_id,
                        status="previewed",
                        collected_count=collected_count,
                        digest_count=digest_count,
                        degraded_sources=degraded_sources,
                    )
                    return RunSummary(
                        run_id=run_id,
                        edition_date=edition_date,
                        collected_count=collected_count,
                        clustered_count=len(clustered),
                        candidate_count=len(candidates),
                        digest_count=digest_count,
                        sent=False,
                        degraded_sources=degraded_sources,
                        output_path=str(output_path),
                        metadata={"model": model_used},
                    )

                pending = database.save_pending_digest(
                    digest=digest,
                    rendered=rendered,
                    recipient_hmac=recipient_hmac,
                )
                message_id = await self._send(
                    client=client,
                    rendered=pending.rendered,
                    recipient=recipient or "",
                    recipient_hmac=recipient_hmac,
                    edition_date=edition_date.isoformat(),
                )
                database.mark_sent(pending.id, message_id)
                database.finish_run(
                    run_id,
                    status="sent",
                    collected_count=collected_count,
                    digest_count=digest_count,
                    degraded_sources=degraded_sources,
                )
                await self._ping_healthcheck(client, failed=False)
                return RunSummary(
                    run_id=run_id,
                    edition_date=edition_date,
                    collected_count=collected_count,
                    clustered_count=len(clustered),
                    candidate_count=len(candidates),
                    digest_count=digest_count,
                    sent=True,
                    degraded_sources=degraded_sources,
                    metadata={"model": model_used},
                )
        except Exception as exc:
            database.finish_run(
                run_id,
                status="failed",
                collected_count=collected_count,
                digest_count=digest_count,
                degraded_sources=degraded_sources,
                error_category=type(exc).__name__,
            )
            logger.error(
                "pipeline_failed",
                extra={"run_id": run_id, "error_category": type(exc).__name__},
            )
            try:
                async with BoundedHttpClient(self._config.network) as health_client:
                    await self._ping_healthcheck(health_client, failed=True)
            except Exception as health_exc:
                logger.warning(
                    "failure_healthcheck_unavailable",
                    extra={"error_category": type(health_exc).__name__},
                )
            raise
        finally:
            database.close()

    async def _collect(self, client: BoundedHttpClient, *, since: datetime) -> CollectionResult:
        adapters: list[SourceAdapter] = [
            FeedAdapter(self._registry, client),
            SitemapAdapter(self._registry, client),
            RedditAdapter(
                self._config.social,
                self._settings,
                client,
                user_agent=self._config.network.user_agent,
            ),
            XAdapter(self._config.social, self._settings, client),
        ]
        results = await asyncio.gather(*(adapter.collect(since=since) for adapter in adapters))
        return CollectionResult(
            stories=[story for result in results for story in result.stories],
            statuses=[status for result in results for status in result.statuses],
        )

    async def _edit(
        self,
        candidates: list[Story],
        *,
        client: BoundedHttpClient,
    ) -> tuple[EditorialResult, str]:
        api_key = secret_value(self._settings.openrouter_api_key)
        if api_key:
            try:
                result = await OpenRouterEditor(
                    self._config.llm,
                    client,
                    api_key=api_key,
                ).edit(candidates, top_n=self._config.newsletter.top_n)
                return result, self._config.llm.model
            except Exception as exc:
                logger.warning(
                    "editorial_fallback",
                    extra={"error_category": type(exc).__name__},
                )
        return (
            deterministic_editorial(candidates, top_n=self._config.newsletter.top_n),
            "deterministic-fallback",
        )

    def _delivery_identity(self, *, required: bool) -> tuple[str | None, str | None]:
        recipient = secret_value(self._settings.email_to)
        privacy_key = secret_value(self._settings.privacy_key)
        if required:
            missing = []
            if not recipient:
                missing.append("FINALBOSS_EMAIL_TO")
            if not privacy_key or len(privacy_key) < 32:
                missing.append("FINALBOSS_PRIVACY_KEY (32+ characters)")
            if not secret_value(self._settings.email_from):
                missing.append("FINALBOSS_EMAIL_FROM")
            if not secret_value(self._settings.resend_api_key):
                missing.append("FINALBOSS_RESEND_API_KEY")
            if missing:
                raise RuntimeError("missing required delivery secrets: " + ", ".join(missing))
        return recipient, privacy_key

    async def _send(
        self,
        *,
        client: BoundedHttpClient,
        rendered: RenderedDigest,
        recipient: str,
        recipient_hmac: str,
        edition_date: str,
        resend_sequence: int | None = None,
    ) -> str:
        api_key = secret_value(self._settings.resend_api_key)
        sender = secret_value(self._settings.email_from)
        if not api_key or not sender:
            raise RuntimeError("email delivery credentials are missing")
        idempotency_key = f"ai-digest/{recipient_hmac}/{edition_date}"
        if resend_sequence is not None:
            idempotency_key = f"{idempotency_key}/resend-{resend_sequence}"
        return await ResendSender(client, api_key=api_key).send(
            rendered,
            sender=sender,
            recipient=recipient,
            idempotency_key=idempotency_key,
        )

    async def _retry_existing(
        self,
        *,
        existing: StoredDigest,
        client: BoundedHttpClient,
        database: Database,
        run_id: str,
        recipient: str,
        recipient_hmac: str,
    ) -> RunSummary:
        try:
            message_id = await self._send(
                client=client,
                rendered=existing.rendered,
                recipient=recipient,
                recipient_hmac=recipient_hmac,
                edition_date=existing.edition_date.isoformat(),
            )
            database.mark_sent(existing.id, message_id)
            database.finish_run(
                run_id,
                status="sent_retry",
                collected_count=0,
                digest_count=0,
                degraded_sources=0,
            )
            return RunSummary(
                run_id=run_id,
                edition_date=existing.edition_date,
                collected_count=0,
                clustered_count=0,
                candidate_count=0,
                digest_count=0,
                sent=True,
                degraded_sources=0,
                metadata={"outcome": "retried_pending_digest"},
            )
        except Exception as exc:
            database.mark_failed(existing.id, type(exc).__name__)
            raise

    async def _force_resend_existing(
        self,
        *,
        existing: StoredDigest,
        client: BoundedHttpClient,
        database: Database,
        run_id: str,
        recipient: str,
        recipient_hmac: str,
    ) -> RunSummary:
        resend = database.reserve_resend(
            existing.id,
            max_resends=self._config.delivery.max_force_resends_per_day,
        )
        try:
            message_id = await self._send(
                client=client,
                rendered=existing.rendered,
                recipient=recipient,
                recipient_hmac=recipient_hmac,
                edition_date=existing.edition_date.isoformat(),
                resend_sequence=resend.sequence,
            )
            database.mark_resend_sent(resend.id, message_id)
            database.finish_run(
                run_id,
                status="force_resent",
                collected_count=0,
                digest_count=0,
                degraded_sources=0,
            )
            await self._ping_healthcheck(client, failed=False)
            return RunSummary(
                run_id=run_id,
                edition_date=existing.edition_date,
                collected_count=0,
                clustered_count=0,
                candidate_count=0,
                digest_count=0,
                sent=True,
                degraded_sources=0,
                metadata={
                    "outcome": "force_resent",
                    "resend_sequence": resend.sequence,
                },
            )
        except Exception as exc:
            database.mark_resend_failed(resend.id, type(exc).__name__)
            raise

    async def _ping_healthcheck(self, client: BoundedHttpClient, *, failed: bool) -> None:
        url = secret_value(self._settings.healthcheck_url)
        if not url:
            return
        target = f"{url.rstrip('/')}/fail" if failed else url
        try:
            await client.request_bytes("GET", target, attempts=1)
        except Exception:
            logger.warning("healthcheck_ping_failed")

    @staticmethod
    def _load_fixture(path: Path) -> CollectionResult:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stories = [Story.model_validate(item) for item in payload]
        return CollectionResult(
            stories=stories,
            statuses=[
                SourceStatus(
                    source_id="fixture",
                    source_kind=SourceKind.RSS,
                    ok=True,
                    item_count=len(stories),
                )
            ],
        )
