from __future__ import annotations

import re
from collections.abc import Sequence

from finalboss.models import (
    EditorialItem,
    LinkedInDraft,
    LinkedInOpportunity,
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
_ARXIV_PREFIX = re.compile(
    r"^arXiv:\S+\s+Announce Type:\s+\w+\s+Abstract:\s*",
    re.IGNORECASE,
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def deterministic_linkedin_draft(story: Story, editorial: EditorialItem) -> LinkedInDraft:
    """Create an honest news-grounded draft when the model output cannot be used."""
    title = clean_text(story.title, limit=150)
    if len(title) < 10:
        title = f"An AI update from {clean_text(story.source_name, limit=80)}"
    source_explanation = _ARXIV_PREFIX.sub("", clean_text(story.excerpt, limit=1200))
    eli5 = _short_grounded_excerpt(source_explanation or editorial.eli5, limit=390)
    why_it_matters = clean_text(editorial.why_it_matters, limit=290)
    return LinkedInDraft(
        topic=title,
        post_lines=[
            f"{title} — the useful question is what changes in practice.",
            eli5,
            why_it_matters,
            (
                "Before changing a roadmap, I would read the primary evidence, test the "
                "claim on a real workflow, and compare the result with the current baseline."
            ),
            "What would you test first?",
        ],
        why_now=(
            "This is the strongest grounded story in today's briefing, so it offers a "
            "timely professional discussion without relying on an invented trend."
        ),
        evidence_item_ids=[story.id],
    )


def build_linkedin_opportunity(
    draft: LinkedInDraft,
    selected: Sequence[SelectedStory],
) -> LinkedInOpportunity:
    """Ground the draft in final email items and compute conservative scores."""
    if not selected:
        raise ValueError("a LinkedIn opportunity requires at least one selected story")
    selected_by_id = {row[0].id: row for row in selected}
    evidence_ids = draft.evidence_item_ids
    if any(item_id not in selected_by_id for item_id in evidence_ids):
        story, editorial, _ = selected[0]
        draft = deterministic_linkedin_draft(story, editorial)
        evidence_ids = draft.evidence_item_ids

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
        topic=draft.topic,
        post_lines=draft.post_lines,
        why_now=draft.why_now,
        impression_potential=impression_potential,
        model_confidence=model_confidence,
        evidence_item_ids=evidence_ids,
    )


def _short_grounded_excerpt(value: str, *, limit: int) -> str:
    normalized = clean_text(value, limit=max(limit * 3, 1200))
    if len(normalized) <= limit:
        return normalized
    sentences = _SENTENCE_BOUNDARY.split(normalized)
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*kept, sentence])
        if len(candidate) > limit:
            break
        kept.append(sentence)
    if kept:
        return " ".join(kept)
    clipped = normalized[: max(1, limit - 1)].rsplit(" ", maxsplit=1)[0].rstrip(".,;:")
    return f"{clipped}…"
