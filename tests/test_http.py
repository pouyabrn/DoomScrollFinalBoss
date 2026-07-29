import pytest
import respx
from httpx import HTTPStatusError, Response

from finalboss.config import NetworkConfig
from finalboss.http import (
    BoundedHttpClient,
    ResponseTooLargeError,
    UnsafeUrlError,
    validate_public_https_url,
)


@pytest.mark.asyncio
@respx.mock
async def test_http_client_follows_only_valid_redirects() -> None:
    respx.get("https://example.com/start").mock(
        return_value=Response(302, headers={"location": "https://example.com/end"})
    )
    respx.get("https://example.com/end").mock(return_value=Response(200, content=b"done"))
    config = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(config) as client:
        body, _, status = await client.request_bytes("GET", "https://example.com/start")
    assert body == b"done"
    assert status == 200


@pytest.mark.asyncio
@respx.mock
async def test_http_client_refuses_authenticated_cross_origin_redirect() -> None:
    origin = respx.get("https://api.example.com/start").mock(
        return_value=Response(302, headers={"location": "https://attacker.example/end"})
    )
    attacker = respx.get("https://attacker.example/end").mock(
        return_value=Response(200, content=b"should not be reached")
    )
    config = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(config) as client:
        with pytest.raises(UnsafeUrlError, match="cross-origin"):
            await client.request_bytes(
                "GET",
                "https://api.example.com/start",
                headers={"Authorization": "Bearer private-test-token"},
            )
    assert origin.called
    assert not attacker.called


def test_url_validator_rejects_embedded_credentials() -> None:
    with pytest.raises(UnsafeUrlError, match="credentials"):
        validate_public_https_url("https://user:password@example.com/feed")


@pytest.mark.asyncio
@respx.mock
async def test_http_client_rejects_large_response() -> None:
    respx.get("https://example.com/large").mock(return_value=Response(200, content=b"x" * 100_001))
    config = NetworkConfig(
        user_agent="FinalBossTest/1.0 (+https://example.com)",
        max_response_bytes=100_000,
    )
    async with BoundedHttpClient(config) as client:
        with pytest.raises(ResponseTooLargeError):
            await client.request_bytes("GET", "https://example.com/large")


@pytest.mark.asyncio
@respx.mock
async def test_get_json_requires_an_object() -> None:
    respx.get("https://example.com/data").mock(return_value=Response(200, json=[1, 2]))
    config = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(config) as client:
        with pytest.raises(ValueError, match="object"):
            await client.get_json("https://example.com/data")


@pytest.mark.asyncio
@respx.mock
async def test_http_client_does_not_retry_permanent_client_errors() -> None:
    route = respx.post("https://example.com/send").mock(
        side_effect=[
            Response(403, json={"message": "forbidden"}),
            Response(200, json={"id": "must-not-be-used"}),
        ]
    )
    config = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(config) as client:
        with pytest.raises(HTTPStatusError):
            await client.post_json(
                "https://example.com/send",
                json_body={"safe": "fixture"},
            )
    assert len(route.calls) == 1
