from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import respx
from httpx import Response

from finalboss.config import NetworkConfig
from finalboss.email.renderer import DigestRenderer, _edition_accent
from finalboss.email.resend import ResendSender
from finalboss.http import BoundedHttpClient
from finalboss.models import (
    Digest,
    DigestItem,
    EditorialItem,
    SourceStatus,
    Story,
)


def _digest(story: Story) -> Digest:
    editorial = EditorialItem(
        item_id=story.id,
        importance=92,
        eli5="A lab made its model better at solving a hard class of problems.",
        why_it_matters="Developers may get stronger results without changing their applications.",
        category="models",
        confidence="high",
    )
    return Digest(
        edition_date=date(2026, 7, 29),
        generated_at=datetime.now(UTC),
        title="Test briefing",
        subtitle="Only useful news.",
        items=[
            DigestItem(
                position=1,
                story=story,
                editorial=editorial,
                final_score=91.5,
            )
        ],
        forecast_lines=[
            "More benchmark details are likely to appear next week.",
            "Early developer tests may show where the release is actually useful.",
        ],
        forecast_confidence="medium",
        source_statuses=[SourceStatus(source_id="test", source_kind="rss", ok=True, item_count=1)],
        model="test-model",
        prompt_version="test-v1",
    )


def test_renderer_escapes_untrusted_content(make_story: Callable[..., Story]) -> None:
    story = make_story(
        title='<img src=x onerror="alert(1)"> Important release',
        excerpt="Details",
    )
    rendered = DigestRenderer().render(_digest(story), subject_prefix="Daily")
    assert "<img src=x" not in rendered.html
    assert "onerror" not in rendered.html
    assert "Important release" in rendered.html
    assert "PREDICTION ENGINE / NEXT 7 DAYS" in rendered.text
    assert "@media only screen and (max-width: 620px)" in rendered.html
    assert "https://example1.com/news/model-launch-1" in rendered.html
    assert "fonts.googleapis.com" not in rendered.html
    assert "javascript:" not in rendered.html


def test_renderer_plain_text_snapshot(make_story: Callable[..., Story]) -> None:
    rendered = DigestRenderer().render(_digest(make_story()), subject_prefix="Daily")
    snapshot = Path("tests/snapshots/digest.txt").read_text(encoding="utf-8").strip()
    assert rendered.text == snapshot


def test_edition_accent_is_stable_and_bounded() -> None:
    edition_date = date(2026, 7, 29)
    assert _edition_accent(edition_date) == _edition_accent(edition_date)
    assert _edition_accent(edition_date) == ("signal-yellow", "#FFF000")
    accents = {_edition_accent(date(2026, 7, day)) for day in range(26, 30)}
    assert len(accents) >= 2


@pytest.mark.asyncio
@respx.mock
async def test_resend_sender_uses_idempotency(make_story: Callable[..., Story]) -> None:
    route = respx.post("https://api.resend.com/emails").mock(
        return_value=Response(200, json={"id": "email_123"})
    )
    rendered = DigestRenderer().render(_digest(make_story()), subject_prefix="Daily")
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(network) as client:
        message_id = await ResendSender(client, api_key="test-key").send(
            rendered,
            sender="Digest <digest@example.com>",
            recipient="owner@example.com",
            idempotency_key="ai-digest/hash/2026-07-29",
        )
    assert message_id == "email_123"
    assert route.calls[0].request.headers["idempotency-key"] == ("ai-digest/hash/2026-07-29")
