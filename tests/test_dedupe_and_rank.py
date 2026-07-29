from collections.abc import Callable
from datetime import UTC, datetime

from finalboss.config import NewsletterConfig
from finalboss.models import EditorialItem, SourceKind, Story
from finalboss.processing.dedupe import cluster_stories
from finalboss.processing.rank import deterministic_rank, final_select


def test_social_signal_merges_into_primary(
    make_story: Callable[..., Story],
) -> None:
    url = "https://publisher.example/major-launch"
    primary = make_story(1, url=url, metrics={"views": 4})
    social = make_story(
        2,
        source_id="reddit",
        source_kind=SourceKind.REDDIT,
        social_only=True,
        url=url,
        metrics={"score": 100, "comments": 20},
    )
    result = cluster_stories([social, primary])
    assert len(result) == 1
    assert result[0].source_id == primary.source_id
    assert result[0].metrics["score"] == 100
    assert result[0].cluster_size == 2
    assert result[0].social_only is False


def test_social_only_story_is_not_rewritten(make_story: Callable[..., Story]) -> None:
    social = make_story(
        1,
        source_id="x",
        source_kind=SourceKind.X,
        social_only=True,
    )
    assert cluster_stories([social]) == []


def test_rank_is_bounded_and_stable(make_story: Callable[..., Story]) -> None:
    stories = [make_story(index, metrics={"likes": index * 100}) for index in range(1, 8)]
    first = deterministic_rank(stories, now=datetime.now(UTC))
    second = deterministic_rank(stories, now=datetime.now(UTC))
    assert [story.id for story in first] == [story.id for story in second]
    assert all(0 <= story.deterministic_score <= 100 for story in first)


def test_final_selection_prefers_source_diversity(make_story: Callable[..., Story]) -> None:
    stories = deterministic_rank(
        [make_story(index, source_id="same-source") for index in range(1, 8)],
        now=datetime.now(UTC),
    )
    editorial = [
        EditorialItem(
            item_id=story.id,
            importance=90,
            eli5="A lab made a useful model easier for ordinary people to use.",
            why_it_matters="More people can use the capability for less money.",
            category="models",
            confidence="high",
        )
        for story in stories
    ]
    config = NewsletterConfig(
        title="Test",
        subtitle="Test subtitle",
        timezone="UTC",
        top_n=2,
        max_items_per_source=2,
    )
    selected = final_select(stories, editorial, config)
    assert len(selected) == 2


def test_final_selection_fills_requested_count_below_score_preference(
    make_story: Callable[..., Story],
) -> None:
    stories = [
        make_story(index).model_copy(update={"deterministic_score": 1.0}) for index in range(1, 4)
    ]
    editorial = [
        EditorialItem(
            item_id=story.id,
            importance=1,
            eli5="A real source published a small but grounded artificial intelligence update.",
            why_it_matters="It completes the requested ranked briefing without inventing a story.",
            category="models",
            confidence="low",
            uncertainty="This item ranked below the preferred score floor.",
        )
        for story in stories
    ]
    config = NewsletterConfig(
        title="Test",
        subtitle="Test subtitle",
        timezone="UTC",
        top_n=2,
        min_story_score=99,
    )
    selected = final_select(stories, editorial, config)
    assert len(selected) == 2
    assert all(row[2] < config.min_story_score for row in selected)
