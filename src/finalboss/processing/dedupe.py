from __future__ import annotations

from collections import defaultdict

from finalboss.models import Story
from finalboss.processing.normalize import title_similarity


def cluster_stories(stories: list[Story]) -> list[Story]:
    by_url: defaultdict[str, list[Story]] = defaultdict(list)
    for story in stories:
        by_url[story.canonical_url].append(story)

    merged = [_merge_cluster(cluster) for cluster in by_url.values()]
    consumed: set[int] = set()
    final: list[Story] = []
    for index, story in enumerate(merged):
        if index in consumed:
            continue
        cluster = [story]
        for other_index in range(index + 1, len(merged)):
            if other_index in consumed:
                continue
            other = merged[other_index]
            hours = abs((story.published_at - other.published_at).total_seconds()) / 3600
            if hours <= 72 and title_similarity(story.title, other.title) >= 0.84:
                cluster.append(other)
                consumed.add(other_index)
        final.append(_merge_cluster(cluster))

    # A social-only URL has no publisher excerpt/title we are permitted to rewrite.
    return [story for story in final if not story.social_only]


def _merge_cluster(cluster: list[Story]) -> Story:
    primary_candidates = [story for story in cluster if not story.social_only]
    primary = max(
        primary_candidates or cluster,
        key=lambda story: (story.source_weight, len(story.excerpt), story.published_at),
    )
    source_names = sorted(
        {
            source_name
            for story in cluster
            for source_name in ([story.source_name] if story.id != primary.id else [])
            + story.corroborating_sources
        }
    )
    metrics: defaultdict[str, int] = defaultdict(int)
    for story in cluster:
        for key, value in story.metrics.items():
            metrics[key] += value
    discussion = primary.discussion_url or next(
        (story.discussion_url for story in cluster if story.discussion_url), None
    )
    return primary.model_copy(
        update={
            "metrics": dict(metrics),
            "corroborating_sources": source_names,
            "discussion_url": discussion,
            "cluster_size": sum(story.cluster_size for story in cluster),
            "social_only": all(story.social_only for story in cluster),
            "published_at": max(story.published_at for story in cluster),
        }
    )
