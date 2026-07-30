from collections.abc import Callable
from typing import Literal

from finalboss.models import EditorialItem, LinkedInDraft, Story
from finalboss.processing.linkedin import (
    build_linkedin_opportunity,
    deterministic_linkedin_draft,
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
    draft = LinkedInDraft(
        topic="Cheaper reasoning changes which AI workflows are practical",
        post_lines=[
            "Cheaper reasoning changes which AI workflows are practical.",
            "Two primary releases point to better capability at a lower operating cost.",
            "That makes previously expensive experiments more realistic for smaller teams.",
            "I would still benchmark one real workflow before changing a roadmap.",
            "Which task would you test first?",
        ],
        why_now="Multiple strong, current sources support a useful professional discussion.",
        evidence_item_ids=[first.id, second.id],
    )
    opportunity = build_linkedin_opportunity(
        draft,
        [
            (first, _editorial(first), 95.0),
            (second, _editorial(second), 90.0),
        ],
    )

    assert 0 <= opportunity.impression_potential <= 90
    assert 0 <= opportunity.model_confidence <= 65
    assert opportunity.signal_basis == "daily-news-only"
    assert opportunity.evidence_item_ids == [first.id, second.id]


def test_linkedin_draft_falls_back_when_evidence_is_not_in_final_digest(
    make_story: Callable[..., Story],
) -> None:
    selected = make_story(1).model_copy(update={"deterministic_score": 80.0})
    omitted = make_story(2)
    draft = LinkedInDraft(
        topic="A topic supported only by an omitted story",
        post_lines=[
            "This hook refers to a story that was omitted from the final digest.",
            "The model could have written more unsupported details in this paragraph.",
            "Those details must not survive when their evidence is unavailable.",
            "The application should replace this entire draft with grounded text.",
        ],
        why_now="This explanation references unavailable evidence and must be replaced.",
        evidence_item_ids=[omitted.id],
    )

    opportunity = build_linkedin_opportunity(
        draft,
        [(selected, _editorial(selected, confidence="low"), 80.0)],
    )

    assert opportunity.evidence_item_ids == [selected.id]
    assert omitted.title not in " ".join(opportunity.post_lines)
    assert "test first" in opportunity.post_lines[-1].casefold()


def test_deterministic_linkedin_draft_uses_complete_grounded_sentence(
    make_story: Callable[..., Story],
) -> None:
    story = make_story(
        excerpt=(
            "arXiv:2607.12345v1 Announce Type: new Abstract: "
            "The study tests whether a documented alignment method transfers across settings. "
            "This second sentence is intentionally very long " + ("evidence " * 100)
        )
    )

    draft = deterministic_linkedin_draft(story, _editorial(story))

    assert draft.post_lines[1] == (
        "The study tests whether a documented alignment method transfers across settings."
    )
    assert "Announce Type" not in draft.post_lines[1]
