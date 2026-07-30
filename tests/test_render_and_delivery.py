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
    LinkedInOpportunity,
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
        linkedin_opportunity=LinkedInOpportunity(
            topic="A reasoning release changes the practical deployment question",
            post_lines=[
                "A better model is interesting. A better model at lower cost is operational.",
                "This release says difficult reasoning tasks can run with a smaller budget.",
                "The important question is whether that holds up in a real team workflow.",
                "I would test one expensive task before changing a production roadmap.",
                "What would you benchmark first?",
            ],
            why_now="The release is fresh, technically relevant, and grounded in a primary source.",
            impression_potential=82,
            model_confidence=47,
            evidence_item_ids=[story.id],
        ),
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
    assert "LINKEDIN POST OPPORTUNITY / NEXT 24 HOURS" in rendered.text
    assert rendered.text.index("PREDICTION ENGINE") < rendered.text.index(
        "LINKEDIN POST OPPORTUNITY"
    )
    assert "@media only screen and (max-width: 620px)" in rendered.html
    assert "https://example1.com/news/model-launch-1" in rendered.html
    assert "fonts.googleapis.com" not in rendered.html
    assert "javascript:" not in rendered.html


def test_renderer_escapes_linkedin_model_text(make_story: Callable[..., Story]) -> None:
    digest = _digest(make_story())
    hostile = digest.linkedin_opportunity.model_copy(
        update={
            "topic": '<img src=x onerror="alert(1)"> A grounded topic',
            "post_lines": [
                '<script>alert("x")</script> A practical release question starts here.',
                "The source describes a documented change to model capability and cost.",
                "The useful test is whether the claim holds in a real professional workflow.",
                "I would compare it with the current baseline before changing a roadmap.",
                "What would you test first?",
            ],
        }
    )
    rendered = DigestRenderer().render(
        digest.model_copy(update={"linkedin_opportunity": hostile}),
        subject_prefix="Daily",
    )
    assert "<script>" not in rendered.html
    assert "onerror" not in rendered.html
    assert "A grounded topic" in rendered.html


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
