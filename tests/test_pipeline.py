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
    assert summary.metadata["linkedin_model"] == "deterministic-fallback"
    assert output.exists()
    html = output.read_text(encoding="utf-8")
    assert "ELI5 / SIMPLE DECODE" in html
    assert "PREDICTION ENGINE // WHAT HAPPENS NEXT" in html
    assert "FINAL UNIT // LINKEDIN POST OPPORTUNITY // NEXT 24H" in html
    assert html.index("PREDICTION ENGINE") < html.index("LINKEDIN POST OPPORTUNITY")


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
        email_to="owner@example.com\nfriend@example.com",
        email_from="Digest <digest@example.com>",
        privacy_key="p" * 32,
    )
    public, registry = load_configuration(settings)
    pipeline = DigestPipeline(settings, public, registry)
    first = await pipeline.run(send=True, fixture=fixture)
    second = await pipeline.run(send=True, fixture=fixture)
    forced = await pipeline.run(send=True, force_resend=True, fixture=fixture)
    assert first.sent is True
    assert second.sent is False
    assert second.metadata["outcome"] == "already_sent"
    assert forced.sent is True
    assert forced.metadata["outcome"] == "force_resent"
    assert forced.metadata["resend_sequence_max"] == 1
    assert len(route.calls) == 4
    original_requests = [json.loads(call.request.content) for call in route.calls[:2]]
    assert {payload["to"][0] for payload in original_requests} == {
        "owner@example.com",
        "friend@example.com",
    }
    assert all(len(payload["to"]) == 1 for payload in original_requests)
    assert original_requests[0]["html"] == original_requests[1]["html"]
    assert (
        route.calls[0].request.headers["idempotency-key"]
        != route.calls[1].request.headers["idempotency-key"]
    )
    assert all(
        call.request.headers["idempotency-key"].endswith("/resend-1") for call in route.calls[2:]
    )
    assert "owner@example.com" not in first.model_dump_json()
    assert "friend@example.com" not in first.model_dump_json()
    assert "owner@example.com" not in forced.model_dump_json()
    database_bytes = (tmp_path / "state.db").read_bytes()
    assert b"owner@example.com" not in database_bytes
    assert b"friend@example.com" not in database_bytes


@pytest.mark.asyncio
@respx.mock
async def test_partial_delivery_retries_only_failed_recipient(
    tmp_path: Path,
    make_story: Callable[..., Story],
) -> None:
    stories = [make_story(index).model_dump(mode="json") for index in range(1, 25)]
    fixture = tmp_path / "stories.json"
    fixture.write_text(json.dumps(stories), encoding="utf-8")
    route = respx.post("https://api.resend.com/emails").mock(
        side_effect=[
            Response(200, json={"id": "email-first"}),
            Response(403, json={"message": "sender rejected"}),
            Response(200, json={"id": "email-retry"}),
        ]
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'partial.db'}",
        config_path=Path("config/newsletter.yaml"),
        sources_path=Path("config/sources.yaml"),
        environment="test",
        resend_api_key="resend-secret",
        email_to="first@example.com\nsecond@example.com",
        email_from="Digest <digest@example.com>",
        privacy_key="p" * 32,
    )
    public, registry = load_configuration(settings)
    pipeline = DigestPipeline(settings, public, registry)

    with pytest.raises(RuntimeError, match="1 recipient deliveries failed"):
        await pipeline.run(send=True, fixture=fixture)
    recovered = await pipeline.run(send=True, fixture=fixture)

    assert recovered.metadata["sent_count"] == 1
    assert recovered.metadata["already_sent_count"] == 1
    assert len(route.calls) == 3
    requests = [json.loads(call.request.content) for call in route.calls]
    assert requests[0]["to"] == ["first@example.com"]
    assert requests[1]["to"] == requests[2]["to"] == ["second@example.com"]
    assert (
        route.calls[1].request.headers["idempotency-key"]
        == route.calls[2].request.headers["idempotency-key"]
    )
    assert requests[1]["html"] == requests[2]["html"]


@pytest.mark.asyncio
@respx.mock
async def test_new_recipient_reuses_todays_stored_edition(
    tmp_path: Path,
    make_story: Callable[..., Story],
) -> None:
    stories = [make_story(index).model_dump(mode="json") for index in range(1, 25)]
    fixture = tmp_path / "stories.json"
    fixture.write_text(json.dumps(stories), encoding="utf-8")
    route = respx.post("https://api.resend.com/emails").mock(
        return_value=Response(200, json={"id": "email-sent"})
    )
    common = {
        "database_url": f"sqlite:///{tmp_path / 'added.db'}",
        "config_path": Path("config/newsletter.yaml"),
        "sources_path": Path("config/sources.yaml"),
        "environment": "test",
        "resend_api_key": "resend-secret",
        "email_from": "Digest <digest@example.com>",
        "privacy_key": "p" * 32,
    }
    first_settings = Settings(**common, email_to="first@example.com")
    public, registry = load_configuration(first_settings)
    await DigestPipeline(first_settings, public, registry).run(send=True, fixture=fixture)

    expanded_settings = Settings(
        **common,
        email_to="second@example.com\nfirst@example.com",
    )
    expanded_public, expanded_registry = load_configuration(expanded_settings)
    expanded = await DigestPipeline(
        expanded_settings,
        expanded_public,
        expanded_registry,
    ).run(send=True, fixture=tmp_path / "fixture-does-not-need-to-exist.json")

    assert expanded.metadata["sent_count"] == 1
    assert expanded.metadata["already_sent_count"] == 1
    assert len(route.calls) == 2
    first_request = json.loads(route.calls[0].request.content)
    second_request = json.loads(route.calls[1].request.content)
    assert first_request["to"] == ["first@example.com"]
    assert second_request["to"] == ["second@example.com"]
    assert first_request["html"] == second_request["html"]


@pytest.mark.asyncio
@respx.mock
async def test_partial_force_resend_retries_only_failed_recipient(
    tmp_path: Path,
    make_story: Callable[..., Story],
) -> None:
    stories = [make_story(index).model_dump(mode="json") for index in range(1, 25)]
    fixture = tmp_path / "stories.json"
    fixture.write_text(json.dumps(stories), encoding="utf-8")
    route = respx.post("https://api.resend.com/emails").mock(
        side_effect=[
            Response(200, json={"id": "original-first"}),
            Response(200, json={"id": "original-second"}),
            Response(200, json={"id": "resend-first"}),
            Response(403, json={"message": "sender rejected"}),
            Response(200, json={"id": "resend-second-retry"}),
        ]
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'partial-force.db'}",
        config_path=Path("config/newsletter.yaml"),
        sources_path=Path("config/sources.yaml"),
        environment="test",
        resend_api_key="resend-secret",
        email_to="first@example.com\nsecond@example.com",
        email_from="Digest <digest@example.com>",
        privacy_key="p" * 32,
    )
    public, registry = load_configuration(settings)
    pipeline = DigestPipeline(settings, public, registry)
    await pipeline.run(send=True, fixture=fixture)

    with pytest.raises(RuntimeError, match="1 recipient resends failed"):
        await pipeline.run(send=True, force_resend=True)
    recovered = await pipeline.run(send=True, force_resend=True)

    assert recovered.metadata["sent_count"] == 1
    assert recovered.metadata["already_resent_count"] == 1
    assert len(route.calls) == 5
    failed = route.calls[3].request
    retried = route.calls[4].request
    assert json.loads(failed.content)["to"] == json.loads(retried.content)["to"]
    assert failed.headers["idempotency-key"] == retried.headers["idempotency-key"]
    assert failed.headers["idempotency-key"].endswith("/resend-1")


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
