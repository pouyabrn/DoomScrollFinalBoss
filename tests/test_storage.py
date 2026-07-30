from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest

from finalboss.models import (
    Digest,
    DigestItem,
    EditorialItem,
    LinkedInOpportunity,
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
        linkedin_opportunity=LinkedInOpportunity(
            topic="A model release changes a practical developer decision",
            why_now="This is the strongest grounded story in the test briefing today.",
            impression_potential=70,
            model_confidence=45,
            evidence_item_ids=[story.id],
        ),
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


def test_force_resend_ledger_retries_then_advances(
    tmp_path: object,
    make_story: Callable[..., Story],
) -> None:
    path = tmp_path.joinpath("state.db")
    database = Database(f"sqlite:///{path}")
    database.initialize(allow_create=True)
    recipient = recipient_fingerprint("owner@example.com", "x" * 32)
    stored = database.save_pending_digest(
        digest=_digest(make_story()),
        rendered=RenderedDigest(subject="Test", html="<p>Test</p>", text="Test"),
        recipient_hmac=recipient,
    )
    database.mark_sent(stored.id, "message-original")

    first = database.reserve_resend(stored.id, max_resends=2)
    assert first.sequence == 1
    database.mark_resend_failed(first.id, "TimeoutError")
    retry = database.reserve_resend(stored.id, max_resends=2)
    assert retry.id == first.id
    assert retry.sequence == 1

    database.mark_resend_sent(retry.id, "message-resend-1")
    second = database.reserve_resend(stored.id, max_resends=2)
    assert second.id != first.id
    assert second.sequence == 2
    database.mark_resend_sent(second.id, "message-resend-2")
    with pytest.raises(ValueError, match="limit"):
        database.reserve_resend(stored.id, max_resends=2)
    database.close()


def test_clone_creates_an_independent_pending_delivery(
    tmp_path: object,
    make_story: Callable[..., Story],
) -> None:
    database = Database(f"sqlite:///{tmp_path.joinpath('clone.db')}")
    database.initialize(allow_create=True)
    original = database.save_pending_digest(
        digest=_digest(make_story()),
        rendered=RenderedDigest(subject="Test", html="<p>Test</p>", text="Test"),
        recipient_hmac=recipient_fingerprint("first@example.com", "x" * 32),
    )
    database.mark_sent(original.id, "message-original")

    clone = database.clone_pending_digest(
        source_digest_id=original.id,
        recipient_hmac=recipient_fingerprint("second@example.com", "x" * 32),
    )

    assert clone.id != original.id
    assert clone.status == "pending"
    assert clone.rendered == original.rendered
    assert clone.item_count == original.item_count == 1
    database.close()


def test_force_resend_batch_retries_only_incomplete_recipients(
    tmp_path: object,
    make_story: Callable[..., Story],
) -> None:
    database = Database(f"sqlite:///{tmp_path.joinpath('batch.db')}")
    database.initialize(allow_create=True)
    rendered = RenderedDigest(subject="Test", html="<p>Test</p>", text="Test")
    first = database.save_pending_digest(
        digest=_digest(make_story(1)),
        rendered=rendered,
        recipient_hmac=recipient_fingerprint("first@example.com", "x" * 32),
    )
    second = database.save_pending_digest(
        digest=_digest(make_story(1)),
        rendered=rendered,
        recipient_hmac=recipient_fingerprint("second@example.com", "x" * 32),
    )
    database.mark_sent(first.id, "message-first")
    database.mark_sent(second.id, "message-second")

    initial = database.reserve_resends([first.id, second.id], max_resends=2)
    database.mark_resend_sent(initial[first.id].id, "resend-first")
    database.mark_resend_failed(initial[second.id].id, "TimeoutError")

    retry = database.reserve_resends([first.id, second.id], max_resends=2)
    assert set(retry) == {second.id}
    assert retry[second.id].id == initial[second.id].id
    database.mark_resend_sent(retry[second.id].id, "resend-second")

    next_batch = database.reserve_resends([first.id, second.id], max_resends=2)
    assert set(next_batch) == {first.id, second.id}
    assert {reservation.sequence for reservation in next_batch.values()} == {2}
    database.close()
