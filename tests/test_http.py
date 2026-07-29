import pytest
import respx
from httpx import Response

from finalboss.config import NetworkConfig
from finalboss.http import BoundedHttpClient, ResponseTooLargeError


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
