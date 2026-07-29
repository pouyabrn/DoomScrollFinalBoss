from collections.abc import Callable
from datetime import UTC, date, datetime

from finalboss.models import (
    Digest,
    DigestItem,
    EditorialItem,
    RenderedDigest,
    Story,
)
from finalboss.storage.database import Database, recipient_fingerprint


def _digest(story: Story) -> Digest:
    editorial = EditorialItem(
        item_id=story.id,
        importance=80,
        eli5="This is a plain explanation of a model release for a normal reader.",
        why_it_matters="It could change the cost of a common developer task.",
        category="models",
        confidence="medium",
    )
    return Digest(
        edition_date=date(2026, 7, 29),
        generated_at=datetime.now(UTC),
        title="Test",
        subtitle="Test",
        items=[DigestItem(position=1, story=story, editorial=editorial, final_score=80)],
        forecast_lines=[
            "More details may arrive next week.",
            "Adoption will probably start slowly.",
        ],
        forecast_confidence="low",
        source_statuses=[],
        model="test",
        prompt_version="test-v1",
    )


def test_database_ledger_is_idempotent(
    tmp_path: object,
    make_story: Callable[..., Story],
) -> None:
    path = tmp_path.joinpath("state.db")
    database = Database(f"sqlite:///{path}")
    database.initialize(allow_create=True)
    recipient = recipient_fingerprint("owner@example.com", "x" * 32)
    rendered = RenderedDigest(subject="Test", html="<p>Test</p>", text="Test")
    first = database.save_pending_digest(
        digest=_digest(make_story()),
        rendered=rendered,
        recipient_hmac=recipient,
    )
    second = database.save_pending_digest(
        digest=_digest(make_story()),
        rendered=rendered,
        recipient_hmac=recipient,
    )
    assert first.id == second.id
    database.mark_sent(first.id, "message-1")
    stored = database.get_digest(edition_date=date(2026, 7, 29), recipient_hmac=recipient)
    assert stored is not None
    assert stored.status == "sent"
    assert len(database.recent_story_fingerprints()) == 1
    database.close()
