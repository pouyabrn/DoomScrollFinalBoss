import pytest
from hypothesis import given
from hypothesis import strategies as st

from finalboss.http import UnsafeUrlError, validate_public_https_url
from finalboss.processing.normalize import canonicalize_url, clean_text, title_similarity


def test_canonicalize_removes_tracking_and_fragment() -> None:
    result = canonicalize_url(
        "https://EXAMPLE.com:443/news/?utm_source=x&b=2&a=1&fbclid=nope#section"
    )
    assert result == "https://example.com/news?a=1&b=2"


@given(st.text(alphabet=st.characters(categories=("Ll", "Nd")), min_size=1, max_size=20))
def test_canonicalization_is_idempotent(path: str) -> None:
    first = canonicalize_url(f"https://example.com/{path}?utm_campaign=test")
    assert canonicalize_url(first) == first


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://localhost/data",
        "https://127.0.0.1/data",
        "file:///etc/passwd",
    ],
)
def test_public_url_validation_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_public_https_url(url)


def test_clean_text_and_similarity() -> None:
    assert clean_text("<p>Hello <b>world</b></p>", limit=100) == "Hello world"
    assert title_similarity("OpenAI launches Model X", "OpenAI releases Model X") > 0.5
