"""Unit tests for URL canonicalisation."""

import pytest
from discovery.canonicalise import canonicalise_url, is_valid_url


def test_is_valid_url():
    assert is_valid_url("https://example.com/post") is True
    assert is_valid_url("http://example.com:8080/path") is True
    assert is_valid_url("ftp://example.com") is False
    assert is_valid_url("not_a_url") is False
    assert is_valid_url("") is False
    assert is_valid_url(None) is False


def test_canonicalise_strips_tracking_params():
    url = "https://EXAMPLE.com/post/?utm_source=twitter&utm_medium=social&utm_campaign=launch"
    clean = canonicalise_url(url)
    assert clean == "https://example.com/post"


def test_canonicalise_strips_fragment():
    url = "https://example.com/article#comments-section"
    clean = canonicalise_url(url)
    assert clean == "https://example.com/article"


def test_canonicalise_preserves_functional_params_sorted():
    url = "https://example.com/view?id=42&view=full&utm_source=rss&category=ai"
    clean = canonicalise_url(url)
    assert clean == "https://example.com/view?category=ai&id=42&view=full"


def test_canonicalise_normalises_slashes_and_ports():
    url = "https://example.com:443//blog//post/"
    clean = canonicalise_url(url)
    assert clean == "https://example.com/blog/post"

    url_root = "http://example.com:80/"
    clean_root = canonicalise_url(url_root)
    assert clean_root == "http://example.com/"


def test_canonicalise_raises_on_invalid_url():
    with pytest.raises(ValueError):
        canonicalise_url("invalid-url-string")
