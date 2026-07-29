from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from finalboss.http import validate_public_https_url

_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}
_TRACKING_PREFIXES = ("utm_",)
_SPACE_RE = re.compile(r"\s+")
_TITLE_TOKEN_RE = re.compile(r"[a-z0-9]+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_text(value: str, *, limit: int) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(value)
        text = " ".join(parser.parts)
    except Exception:
        text = value
    return _SPACE_RE.sub(" ", html.unescape(text)).strip()[:limit]


def canonicalize_url(url: str) -> str:
    validate_public_https_url(url)
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = hostname if port in {None, 443} else f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    return urlunsplit(("https", netloc, path, urlencode(sorted(query)), ""))


def story_id(source_id: str, external_id: str) -> str:
    digest = hashlib.sha256(f"{source_id}\0{external_id}".encode()).hexdigest()[:20]
    return f"{source_id}-{digest}"


def fingerprint(canonical_url: str, title: str) -> str:
    normalized = " ".join(_TITLE_TOKEN_RE.findall(title.lower()))
    return hashlib.sha256(f"{canonical_url}\0{normalized}".encode()).hexdigest()


def normalized_title_tokens(title: str) -> set[str]:
    return set(_TITLE_TOKEN_RE.findall(title.lower()))


def title_similarity(left: str, right: str) -> float:
    left_tokens = normalized_title_tokens(left)
    right_tokens = normalized_title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
