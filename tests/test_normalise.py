"""Unit tests for HTML stripping, date parsing, and feed entry normalisation."""

from datetime import datetime, timezone
import pytest
from discovery.normalise import (
    generate_post_id,
    normalise_feed_entry,
    parse_date_to_iso,
    strip_html,
)


def test_strip_html_basic_and_entities():
    html_input = "<p>Building a <b>RAG</b> pipeline &amp; evaluating precision@k.</p>"
    clean = strip_html(html_input)
    assert clean == "Building a RAG pipeline & evaluating precision@k."


def test_strip_html_removes_scripts_and_iframes():
    html_input = "<script>alert('hack');</script><p>Clean content</p><iframe src='evil.com'></iframe>"
    clean = strip_html(html_input)
    assert clean == "Clean content"
    assert "hack" not in clean


def test_strip_html_empty_or_none():
    assert strip_html("") == ""
    assert strip_html(None) == ""


def test_parse_date_to_iso_valid():
    rfc_date = "Fri, 20 Nov 2026 12:00:00 GMT"
    iso = parse_date_to_iso(rfc_date)
    assert iso == "2026-11-20T12:00:00Z"

    iso_input = "2026-11-20T17:30:00+05:30"
    iso_out = parse_date_to_iso(iso_input)
    assert iso_out == "2026-11-20T12:00:00Z"


def test_parse_date_to_iso_invalid_or_missing():
    assert parse_date_to_iso("not-a-real-date") is None
    assert parse_date_to_iso("") is None
    assert parse_date_to_iso(None) is None


def test_generate_post_id_deterministic():
    url = "https://example.com/post-one"
    id1 = generate_post_id(url)
    id2 = generate_post_id(url)
    assert id1 == id2
    assert len(id1) == 16
    assert id1 != generate_post_id("https://example.com/post-two")


def test_normalise_feed_entry_valid():
    entry = {
        "title": "Production RAG <b>Architecture</b>",
        "link": "https://example.com/post?utm_source=feed#tag",
        "summary": "<p>A detailed case study on hybrid search and latency.</p>",
        "author": "Alice Engineer",
        "published": "Thu, 19 Nov 2026 10:00:00 GMT",
    }
    fixed_time = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    res = normalise_feed_entry(entry, source_name="Tech Blog", discovery_time=fixed_time)
    assert res is not None
    assert res["title"] == "Production RAG Architecture"
    assert res["canonical_url"] == "https://example.com/post"
    assert res["post_url"] == "https://example.com/post?utm_source=feed#tag"
    assert res["author_name"] == "Alice Engineer"
    assert res["published_at"] == "2026-11-19T10:00:00Z"
    assert res["discovered_at"] == "2026-11-21T10:00:00Z"


def test_normalise_feed_entry_rejects_missing_title_or_link():
    # Missing title
    no_title = {"link": "https://example.com/p1", "summary": "Some text"}
    assert normalise_feed_entry(no_title, source_name="Test") is None

    # Missing link
    no_link = {"title": "Good Title", "summary": "Some text"}
    assert normalise_feed_entry(no_link, source_name="Test") is None


def test_normalise_feed_entry_truncates_summary():
    entry = {
        "title": "Long Post",
        "link": "https://example.com/long",
        "summary": "x" * 10000,
    }
    res = normalise_feed_entry(entry, source_name="Test", max_text_length=500)
    assert res is not None
    assert len(res["post_text"]) == 500
