from collections.abc import Callable
from typing import Literal

from finalboss.models import EditorialItem, LinkedInTopic, Story
from finalboss.processing.linkedin import (
    build_linkedin_opportunity,
    deterministic_linkedin_topic,
)


def _editorial(
    story: Story,
    *,
    confidence: Literal["low", "medium", "high"] = "high",
) -> EditorialItem:
    return EditorialItem(
        item_id=story.id,
        importance=90,
        eli5="A lab documented a cheaper way to run a stronger reasoning model.",
        why_it_matters="Teams may be able to test difficult workflows on a smaller budget.",
        category="models",
        confidence=confidence,
    )


def test_linkedin_scores_are_bounded_and_application_computed(
    make_story: Callable[..., Story],
) -> None:
    first = make_story(1).model_copy(update={"deterministic_score": 95.0, "cluster_size": 4})
    second = make_story(2).model_copy(update={"deterministic_score": 90.0, "cluster_size": 3})
    topic = LinkedInTopic(
        topic="Cheaper reasoning changes which AI workflows are practical",
        why_now="Multiple strong, current sources support a useful professional discussion.",
        evidence_item_ids=[first.id, second.id],
    )
    opportunity = build_linkedin_opportunity(
        topic,
        [
            (first, _editorial(first), 95.0),
            (second, _editorial(second), 90.0),
        ],
    )

    assert 0 <= opportunity.impression_potential <= 90
    assert 0 <= opportunity.model_confidence <= 65
    assert opportunity.signal_basis == "daily-news-only"
    assert opportunity.evidence_item_ids == [first.id, second.id]


def test_linkedin_topic_falls_back_when_evidence_is_not_in_final_digest(
    make_story: Callable[..., Story],
) -> None:
    selected = make_story(1).model_copy(update={"deterministic_score": 80.0})
    omitted = make_story(2)
    topic = LinkedInTopic(
        topic="A topic supported only by an omitted story",
        why_now="This explanation references unavailable evidence and must be replaced.",
        evidence_item_ids=[omitted.id],
    )

    opportunity = build_linkedin_opportunity(
        topic,
        [(selected, _editorial(selected, confidence="low"), 80.0)],
    )

    assert opportunity.evidence_item_ids == [selected.id]
    assert opportunity.topic == selected.title
    assert "strongest grounded story" in opportunity.why_now


def test_deterministic_linkedin_topic_is_grounded(
    make_story: Callable[..., Story],
) -> None:
    story = make_story()

    topic = deterministic_linkedin_topic(story, _editorial(story))

    assert topic.topic == story.title
    assert _editorial(story).why_it_matters in topic.why_now
    assert topic.evidence_item_ids == [story.id]
