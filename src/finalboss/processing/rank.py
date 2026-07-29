from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime

from finalboss.config import NewsletterConfig
from finalboss.models import EditorialItem, Story, TrustTier

_HIGH_IMPACT = re.compile(
    r"\b("
    r"launch|release|announce|open.?source|regulation|law|security|breach|"
    r"funding|acquisition|benchmark|state.?of.?the.?art|sota|price|"
    r"agent|model|reasoning|multimodal|robot|chip|training"
    r")\b",
    re.IGNORECASE,
)
_CLICKBAIT = re.compile(r"\b(shocking|mind.?blowing|you won.t believe|game.?changer)\b", re.I)
_TIER_POINTS = {
    TrustTier.PRIMARY: 24.0,
    TrustTier.RESEARCH: 21.0,
    TrustTier.EXPERT: 19.0,
    TrustTier.PRESS: 13.0,
    TrustTier.SOCIAL: 7.0,
}


def deterministic_rank(stories: list[Story], *, now: datetime) -> list[Story]:
    ranked = [
        story.model_copy(update={"deterministic_score": _score(story, now)}) for story in stories
    ]
    return sorted(
        ranked,
        key=lambda story: (
            -story.deterministic_score,
            -story.published_at.timestamp(),
            story.id,
        ),
    )


def _score(story: Story, now: datetime) -> float:
    age_hours = max(0.0, (now - story.published_at).total_seconds() / 3600)
    recency = 25.0 * math.exp(-age_hours / 28.0)
    authority = _TIER_POINTS[story.trust_tier] * story.source_weight
    corroboration = min(14.0, 5.0 * math.log1p(max(0, story.cluster_size - 1)))
    engagement_total = sum(max(0, value) for value in story.metrics.values())
    engagement = min(12.0, 2.2 * math.log1p(engagement_total))
    text = f"{story.title} {story.excerpt[:500]}"
    importance = min(18.0, len(_HIGH_IMPACT.findall(text)) * 2.5)
    clickbait_penalty = 10.0 if _CLICKBAIT.search(story.title) else 0.0
    missing_evidence_penalty = 5.0 if not story.excerpt else 0.0
    return round(
        max(
            0.0,
            min(
                100.0,
                recency
                + authority
                + corroboration
                + engagement
                + importance
                - clickbait_penalty
                - missing_evidence_penalty,
            ),
        ),
        3,
    )


def final_select(
    candidates: list[Story],
    editorial: list[EditorialItem],
    config: NewsletterConfig,
) -> list[tuple[Story, EditorialItem, float]]:
    candidate_by_id = {story.id: story for story in candidates}
    editorial_by_id = {item.item_id: item for item in editorial if item.item_id in candidate_by_id}
    all_scored: list[tuple[Story, EditorialItem, float]] = []
    for story in candidates:
        item = editorial_by_id.get(story.id)
        if item is None:
            continue
        final_score = round((0.58 * item.importance) + (0.42 * story.deterministic_score), 3)
        all_scored.append((story, item, final_score))
    all_scored.sort(key=lambda row: (-row[2], row[0].id))
    scored = [row for row in all_scored if row[2] >= config.min_story_score]

    selected: list[tuple[Story, EditorialItem, float]] = []
    sources: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    for row in scored:
        story, item, _ = row
        category = item.category.lower()
        if sources[story.source_id] >= config.max_items_per_source:
            continue
        if categories[category] >= config.max_items_per_category:
            continue
        selected.append(row)
        sources[story.source_id] += 1
        categories[category] += 1
        if len(selected) >= config.top_n:
            break
    if len(selected) >= config.top_n:
        return selected

    # Category limits are a diversity preference, not a reason to omit a credible
    # story when the user explicitly requested a top-20 briefing.
    selected_ids = {story.id for story, _, _ in selected}
    for row in scored:
        story, _, _ = row
        if story.id in selected_ids:
            continue
        if sources[story.source_id] >= config.max_items_per_source:
            continue
        selected.append(row)
        selected_ids.add(story.id)
        sources[story.source_id] += 1
        if len(selected) >= config.top_n:
            break
    if len(selected) >= config.top_n:
        return selected

    # Source caps are also soft. If the editorial model returned exactly N credible
    # items, preserve the requested briefing size instead of silently dropping some.
    for row in scored:
        story, _, _ = row
        if story.id in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(story.id)
        if len(selected) >= config.top_n:
            break
    if len(selected) >= config.top_n:
        return selected

    # The score floor is a ranking preference. Every row here is still a real,
    # grounded candidate selected or backed by editorial data. Fill the requested
    # briefing size from the strongest remaining rows instead of silently shrinking it.
    for row in all_scored:
        story, _, _ = row
        if story.id in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(story.id)
        if len(selected) >= config.top_n:
            break
    return selected
