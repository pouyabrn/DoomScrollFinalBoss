import json
from collections.abc import Callable
from pathlib import Path

import pytest
import respx
from httpx import Response

from finalboss.config import Settings, load_configuration
from finalboss.models import Story
from finalboss.pipeline import DigestPipeline


@pytest.mark.asyncio
async def test_fixture_pipeline_builds_top_twenty_without_network(
    tmp_path: Path,
    make_story: Callable[..., Story],
) -> None:
    stories = [make_story(index).model_dump(mode="json") for index in range(1, 25)]
    fixture = tmp_path / "stories.json"
    fixture.write_text(json.dumps(stories), encoding="utf-8")
    output = tmp_path / "preview.html"
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'state.db'}",
        config_path=Path("config/newsletter.yaml"),
        sources_path=Path("config/sources.yaml"),
        environment="test",
    )
    public, registry = load_configuration(settings)
    summary = await DigestPipeline(settings, public, registry).run(
        send=False,
        fixture=fixture,
        output=output,
    )
    assert summary.digest_count == 20
    assert summary.sent is False
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "Explain like I" in html
    assert "What probably happens next week" in html


@pytest.mark.asyncio
@respx.mock
async def test_send_pipeline_is_idempotent_across_runs(
    tmp_path: Path,
    make_story: Callable[..., Story],
) -> None:
    stories = [make_story(index).model_dump(mode="json") for index in range(1, 25)]
    fixture = tmp_path / "stories.json"
    fixture.write_text(json.dumps(stories), encoding="utf-8")
    route = respx.post("https://api.resend.com/emails").mock(
        return_value=Response(200, json={"id": "email-first"})
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'state.db'}",
        config_path=Path("config/newsletter.yaml"),
        sources_path=Path("config/sources.yaml"),
        environment="test",
        resend_api_key="resend-secret",
        email_to="owner@example.com",
        email_from="Digest <digest@example.com>",
        privacy_key="p" * 32,
    )
    public, registry = load_configuration(settings)
    pipeline = DigestPipeline(settings, public, registry)
    first = await pipeline.run(send=True, fixture=fixture)
    second = await pipeline.run(send=True, fixture=fixture)
    assert first.sent is True
    assert second.sent is False
    assert second.metadata["outcome"] == "already_sent"
    assert len(route.calls) == 1
    assert "owner@example.com" not in first.model_dump_json()


@pytest.mark.asyncio
async def test_empty_fixture_fails_without_sending(tmp_path: Path) -> None:
    fixture = tmp_path / "stories.json"
    fixture.write_text("[]", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'state.db'}",
        config_path=Path("config/newsletter.yaml"),
        sources_path=Path("config/sources.yaml"),
        environment="test",
    )
    public, registry = load_configuration(settings)
    with pytest.raises(RuntimeError, match="no credible"):
        await DigestPipeline(settings, public, registry).run(
            send=False,
            fixture=fixture,
            output=tmp_path / "never.html",
        )
