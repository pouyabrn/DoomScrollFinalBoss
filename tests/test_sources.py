from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
import respx
from httpx import Response

from finalboss.config import NetworkConfig, Settings, SocialConfig
from finalboss.http import BoundedHttpClient
from finalboss.models import (
    FeedDefinition,
    SitemapDefinition,
    SourceKind,
    SourceRegistry,
    Story,
)
from finalboss.sources.feeds import FeedAdapter
from finalboss.sources.reddit import RedditAdapter
from finalboss.sources.sitemaps import SitemapAdapter
from finalboss.sources.x import XAdapter


@pytest.mark.asyncio
@respx.mock
async def test_feed_adapter_parses_and_sanitizes() -> None:
    url = "https://feeds.example/rss"
    respx.get(url).mock(
        return_value=Response(
            200,
            text="""<?xml version="1.0"?>
            <rss version="2.0"><channel><title>Test</title><item>
            <title><![CDATA[Major <b>model</b> launch]]></title>
            <link>https://publisher.example/story?utm_source=feed</link>
            <guid>story-1</guid>
            <pubDate>Wed, 29 Jul 2026 10:00:00 GMT</pubDate>
            <description><![CDATA[<script>bad()</script><p>Useful details.</p>]]></description>
            </item></channel></rss>""",
        )
    )
    registry = SourceRegistry(
        feeds=[
            FeedDefinition(
                id="fixture-feed",
                name="Fixture",
                url=url,
                category="models",
                tier="primary",
                weight=1,
                max_items=5,
                terms_note="Test fixture.",
            )
        ]
    )
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(network) as client:
        result = await FeedAdapter(registry, client).collect(
            since=datetime(2026, 7, 28, tzinfo=UTC)
        )
    assert result.statuses[0].ok
    assert result.stories[0].url == "https://publisher.example/story"
    assert "<" not in result.stories[0].title


def test_x_adapter_keeps_external_link_as_social_signal(
    make_story: Callable[..., Story],
) -> None:
    del make_story
    story = XAdapter._story(
        {
            "id": "123",
            "author_id": "9",
            "created_at": datetime.now(UTC).isoformat(),
            "text": "Read this release",
            "entities": {
                "urls": [{"expanded_url": "https://publisher.example/release?utm_source=x"}]
            },
            "public_metrics": {"like_count": 12, "retweet_count": 4},
        },
        users={"9": "OfficialLab"},
    )
    assert story is not None
    assert story.source_kind == SourceKind.X
    assert story.social_only is True
    assert story.discussion_url == "https://x.com/OfficialLab/status/123"


@pytest.mark.asyncio
@respx.mock
async def test_broken_feed_is_isolated() -> None:
    url = "https://feeds.example/broken"
    respx.get(url).mock(return_value=Response(503))
    registry = SourceRegistry(
        feeds=[
            FeedDefinition(
                id="broken-feed",
                name="Broken",
                url=url,
                category="press",
                tier="press",
                weight=0.5,
                max_items=5,
                terms_note="Test fixture.",
            )
        ]
    )
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(network) as client:
        result = await FeedAdapter(registry, client).collect(
            since=datetime.now(UTC) - timedelta(days=1)
        )
    assert result.stories == []
    assert result.statuses[0].ok is False


@pytest.mark.asyncio
@respx.mock
async def test_reddit_adapter_uses_oauth_and_external_links() -> None:
    respx.post("https://www.reddit.com/api/v1/access_token").mock(
        return_value=Response(200, json={"access_token": "oauth-token"})
    )
    listing = {
        "data": {
            "children": [
                {
                    "data": {
                        "name": "t3_abc",
                        "title": "A linked model release",
                        "url_overridden_by_dest": "https://publisher.example/release",
                        "permalink": "/r/MachineLearning/comments/abc/release/",
                        "created_utc": datetime.now(UTC).timestamp(),
                        "score": 42,
                        "num_comments": 7,
                        "is_self": False,
                    }
                }
            ]
        }
    }
    route = respx.get(url__startswith="https://oauth.reddit.com/r/").mock(
        return_value=Response(200, json=listing)
    )
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    settings = Settings(reddit_client_id="client", reddit_client_secret="secret")
    social = SocialConfig(reddit_subreddits=["MachineLearning"])
    async with BoundedHttpClient(network) as client:
        result = await RedditAdapter(
            social,
            settings,
            client,
            user_agent=network.user_agent,
        ).collect(since=datetime.now(UTC) - timedelta(days=1))
    assert result.statuses[0].ok
    assert len(result.stories) == 1
    assert result.stories[0].social_only is True
    assert len(route.calls) == 2


@pytest.mark.asyncio
async def test_social_adapters_fail_closed_without_credentials() -> None:
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    settings = Settings()
    social = SocialConfig(reddit_subreddits=["MachineLearning"], x_accounts=["OpenAI"])
    async with BoundedHttpClient(network) as client:
        reddit = await RedditAdapter(
            social, settings, client, user_agent=network.user_agent
        ).collect(since=datetime.now(UTC) - timedelta(days=1))
        x_result = await XAdapter(social, settings, client).collect(
            since=datetime.now(UTC) - timedelta(days=1)
        )
    assert reddit.statuses[0].skipped
    assert x_result.statuses[0].skipped


@pytest.mark.asyncio
@respx.mock
async def test_x_adapter_uses_one_bounded_recent_search() -> None:
    route = respx.get("https://api.x.com/2/tweets/search/recent").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "id": "999",
                        "author_id": "1",
                        "created_at": datetime.now(UTC).isoformat(),
                        "text": "Release details",
                        "entities": {
                            "urls": [{"expanded_url": "https://publisher.example/model-release"}]
                        },
                        "public_metrics": {"like_count": 9},
                    }
                ],
                "includes": {"users": [{"id": "1", "username": "OpenAI"}]},
            },
        )
    )
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    settings = Settings(x_bearer_token="bearer")
    social = SocialConfig(x_accounts=["OpenAI"], x_max_posts_per_day=10)
    async with BoundedHttpClient(network) as client:
        result = await XAdapter(social, settings, client).collect(
            since=datetime.now(UTC) - timedelta(days=1)
        )
    assert result.statuses[0].ok
    assert result.stories[0].discussion_url == "https://x.com/OpenAI/status/999"
    assert route.calls[0].request.url.params["max_results"] == "10"


@pytest.mark.asyncio
@respx.mock
async def test_sitemap_adapter_reads_metadata_without_page_scraping() -> None:
    sitemap_url = "https://lab.example/sitemap.xml"
    respx.get(sitemap_url).mock(
        return_value=Response(
            200,
            text="""<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url>
                <loc>https://lab.example/news/new-reasoning-model</loc>
                <lastmod>2026-07-29T10:00:00Z</lastmod>
              </url>
              <url>
                <loc>https://lab.example/about</loc>
                <lastmod>2026-07-29</lastmod>
              </url>
            </urlset>""",
        )
    )
    registry = SourceRegistry(
        feeds=[],
        sitemaps=[
            SitemapDefinition(
                id="lab-sitemap",
                name="Lab",
                url=sitemap_url,
                include_pattern="/news/",
                category="labs",
                tier="primary",
                weight=1,
                terms_note="Test fixture.",
            )
        ],
    )
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(network) as client:
        result = await SitemapAdapter(registry, client).collect(
            since=datetime(2026, 7, 28, tzinfo=UTC)
        )
    assert result.statuses[0].ok
    assert len(result.stories) == 1
    assert result.stories[0].title == "New Reasoning Model"
