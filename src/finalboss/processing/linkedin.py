from __future__ import annotations

from collections.abc import Sequence

from finalboss.models import (
    EditorialItem,
    LinkedInOpportunity,
    LinkedInTopic,
    Story,
    TrustTier,
)
from finalboss.processing.normalize import clean_text

SelectedStory = tuple[Story, EditorialItem, float]

_EDITORIAL_CONFIDENCE_POINTS = {"low": 5, "medium": 10, "high": 15}
_TIER_CONFIDENCE_POINTS = {
    TrustTier.SOCIAL: 0,
    TrustTier.PRESS: 4,
    TrustTier.EXPERT: 7,
    TrustTier.RESEARCH: 10,
    TrustTier.PRIMARY: 12,
}


def deterministic_linkedin_topic(story: Story, editorial: EditorialItem) -> LinkedInTopic:
    """Create an honest news-grounded topic when the model output cannot be used."""
    title = clean_text(story.title, limit=150)
    if len(title) < 10:
        title = f"An AI update from {clean_text(story.source_name, limit=80)}"
    why_it_matters = clean_text(editorial.why_it_matters, limit=170)
    return LinkedInTopic(
        topic=title,
        why_now=(
            f"{why_it_matters} It is the strongest grounded story in today's briefing, "
            "making it a timely professional discussion."
        ),
        evidence_item_ids=[story.id],
    )


def build_linkedin_opportunity(
    topic: LinkedInTopic,
    selected: Sequence[SelectedStory],
) -> LinkedInOpportunity:
    """Ground the topic in final email items and compute conservative scores."""
    if not selected:
        raise ValueError("a LinkedIn opportunity requires at least one selected story")
    selected_by_id = {row[0].id: row for row in selected}
    evidence_ids = topic.evidence_item_ids
    if any(item_id not in selected_by_id for item_id in evidence_ids):
        story, editorial, _ = selected[0]
        topic = deterministic_linkedin_topic(story, editorial)
        evidence_ids = topic.evidence_item_ids

    evidence = [selected_by_id[item_id] for item_id in evidence_ids]
    mean_final_score = sum(row[2] for row in evidence) / len(evidence)
    evidence_bonus = min(6, max(0, len(evidence) - 1) * 3)
    impression_potential = round(
        min(90.0, max(20.0, 20.0 + 0.68 * mean_final_score + evidence_bonus))
    )

    editorial_confidence = round(
        sum(_EDITORIAL_CONFIDENCE_POINTS[row[1].confidence] for row in evidence) / len(evidence)
    )
    source_confidence = round(
        sum(_TIER_CONFIDENCE_POINTS[row[0].trust_tier] for row in evidence) / len(evidence)
    )
    source_diversity = min(6, max(0, len({row[0].source_id for row in evidence}) - 1) * 3)
    corroboration = min(
        10,
        sum(max(0, row[0].cluster_size - 1) for row in evidence) * 2,
    )
    model_confidence = min(
        65,
        20
        + editorial_confidence
        + source_confidence
        + min(8, max(0, len(evidence) - 1) * 4)
        + source_diversity
        + corroboration,
    )

    return LinkedInOpportunity(
        topic=topic.topic,
        why_now=topic.why_now,
        impression_potential=impression_potential,
        model_confidence=model_confidence,
        evidence_item_ids=evidence_ids,
    )
