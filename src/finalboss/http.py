from __future__ import annotations

import asyncio
import ipaddress
import secrets
from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from finalboss.config import NetworkConfig


class UnsafeUrlError(ValueError):
    pass


class ResponseTooLargeError(ValueError):
    pass


_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "proxy-authorization",
        "x-api-key",
    }
)


def validate_public_https_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeUrlError("only absolute HTTPS URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("credentials in URLs are not allowed")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".local", ".internal", ".localhost")):
        raise UnsafeUrlError("local hostnames are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise UnsafeUrlError("private or reserved IP addresses are not allowed")


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    return (
        parsed.scheme.lower(),
        (parsed.hostname or "").lower().rstrip("."),
        parsed.port or 443,
    )


class BoundedHttpClient:
    def __init__(self, config: NetworkConfig) -> None:
        self._config = config
        self._global = asyncio.Semaphore(config.concurrency)
        self._per_host: defaultdict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(config.per_host_concurrency)
        )
        timeout = httpx.Timeout(
            timeout=config.timeout_seconds,
            connect=min(config.timeout_seconds, 10),
        )
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "User-Agent": config.user_agent,
                "Accept": (
                    "application/rss+xml, application/atom+xml, application/json, "
                    "text/xml;q=0.9, */*;q=0.5"
                ),
            },
        )

    async def __aenter__(self) -> BoundedHttpClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self._client.aclose()

    async def request_bytes(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
        data: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        auth: httpx.Auth | tuple[str, str] | None = None,
        attempts: int = 3,
    ) -> tuple[bytes, httpx.Headers, int]:
        validate_public_https_url(url)
        current_url = url
        request_headers = headers
        request_params = params
        redirects = 0
        for attempt in range(1, attempts + 1):
            hostname = urlsplit(current_url).hostname or ""
            try:
                async with (
                    self._global,
                    self._per_host[hostname],
                    self._client.stream(
                        method,
                        current_url,
                        headers=request_headers,
                        params=request_params,
                        data=data,
                        json=json_body,
                        auth=auth,
                    ) as response,
                ):
                    if response.is_redirect:
                        if redirects >= 3:
                            raise httpx.TooManyRedirects("redirect limit exceeded")
                        location = response.headers.get("location")
                        if not location:
                            response.raise_for_status()
                        redirected_url = urljoin(current_url, location)
                        validate_public_https_url(redirected_url)
                        if _origin(redirected_url) != _origin(current_url):
                            sensitive_headers = {
                                name.lower() for name in (request_headers or {})
                            } & _SENSITIVE_HEADERS
                            if auth is not None or sensitive_headers or method.upper() != "GET":
                                raise UnsafeUrlError(
                                    "authenticated or state-changing cross-origin redirect refused"
                                )
                            request_headers = None
                            request_params = None
                        current_url = redirected_url
                        redirects += 1
                        continue
                    if response.status_code in {429, 500, 502, 503, 504}:
                        response.raise_for_status()
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._config.max_response_bytes:
                            raise ResponseTooLargeError("response exceeded configured byte limit")
                    return bytes(body), response.headers, response.status_code
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                if attempt >= attempts:
                    raise
                retry_after = 0.0
                if "response" in locals() and response.status_code in {429, 503}:
                    try:
                        retry_after = float(response.headers.get("retry-after", "0"))
                    except ValueError:
                        retry_after = 0.0
                jitter = secrets.randbelow(1000) / 1000
                delay = min(30.0, max(retry_after, (2 ** (attempt - 1)) + jitter))
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable HTTP retry state")

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
        attempts: int = 3,
    ) -> dict[str, Any]:
        body, _, _ = await self.request_bytes(
            "GET", url, headers=headers, params=params, attempts=attempts
        )
        parsed = httpx.Response(200, content=body).json()
        if not isinstance(parsed, dict):
            raise ValueError("expected JSON object")
        return parsed

    async def post_json(
        self,
        url: str,
        *,
        json_body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
        attempts: int = 3,
    ) -> dict[str, Any]:
        body, _, _ = await self.request_bytes(
            "POST",
            url,
            headers=headers,
            json_body=json_body,
            attempts=attempts,
        )
        parsed = httpx.Response(200, content=body).json()
        if not isinstance(parsed, dict):
            raise ValueError("expected JSON object")
        return parsed
