import pytest

from src.web import WebFetchError, validate_public_url


def test_accepts_public_https_url_without_fragment():
    assert validate_public_url("https://example.com/docs?q=ai#section") == "https://example.com/docs?q=ai"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8501",
        "http://127.0.0.1",
        "http://10.0.0.2/private",
        "file:///etc/passwd",
        "https://user:secret@example.com",
        "https://example.com:8080",
    ],
)
def test_rejects_non_public_or_unsafe_targets(url):
    with pytest.raises(WebFetchError):
        validate_public_url(url)
