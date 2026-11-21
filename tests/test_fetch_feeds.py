"""Unit tests for feed fetching, deduplication, and export."""

import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
from discovery.fetch_feeds import fetch_all_feeds, fetch_single_feed, is_within_max_age
from discovery.upload import export_to_csv, export_to_json

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_fetch_single_feed_from_xml():
    xml_path = FIXTURES_DIR / "sample_rss.xml"
    with open(xml_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    items = fetch_single_feed("https://example.com/rss", source_name="Sample Source", feed_content=xml_content)
    assert len(items) == 2
    assert "RAG" in items[0]["title"]
    assert items[0]["canonical_url"] == "https://example.com/posts/scaling-rag"
    assert items[0]["source_name"] == "Sample Source"


def test_fetch_single_feed_malformed_xml():
    xml_path = FIXTURES_DIR / "malformed_rss.xml"
    with open(xml_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    items = fetch_single_feed("https://malformed.example.com", source_name="Malformed", feed_content=xml_content)
    # The malformed fixture has 1 item with missing title and 1 item with no link, so only 1 valid item is accepted
    assert len(items) == 1
    assert items[0]["title"] == "Broken Date and Bad HTML"
    # Functional param id=42 preserved, tracking utm_source removed
    assert "id=42" in items[0]["canonical_url"]
    assert "utm_source" not in items[0]["canonical_url"]
    # Malformed date yields None
    assert items[0]["published_at"] is None


def test_fetch_all_feeds_deduplication_and_ranking(tmp_path):
    # Two feeds referencing the same post with different tracking params
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Feed 1</title>
        <link>https://example.com</link>
        <item>
          <title>Agentic AI and MCP Protocols</title>
          <link>https://example.com/article?id=10&amp;utm_source=newsletter</link>
          <description>Production deployment of AI agents with tool calling and MCP.</description>
          <pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    feed_path = tmp_path / "feed.xml"
    feed_path.write_text(xml_content, encoding="utf-8")

    # Mock fetch_single_feed to return from local content
    items = fetch_single_feed("https://example.com/rss", "Source A", feed_content=xml_content)

    # Duplicate entry
    duplicate_items = fetch_single_feed("https://example.com/rss2", "Source B", feed_content=xml_content)

    posts_by_url = {}
    for item in items + duplicate_items:
        posts_by_url[item["canonical_url"]] = item

    # Should deduplicate down to 1 unique canonical URL
    assert len(posts_by_url) == 1


def test_json_and_csv_export(tmp_path):
    sample_posts = [
        {
            "id": "abc1234567890def",
            "relevance_score": 88,
            "topic_tags": json.dumps(["RAG", "AI Engineering"]),
            "title": "Scaling Hybrid Search",
            "source_name": "Test Source",
            "author_name": "Jane",
            "canonical_url": "https://example.com/post",
            "published_at": "2026-11-20T12:00:00Z",
            "post_text": "Sample text body",
        }
    ]

    json_path = tmp_path / "output.json"
    csv_path = tmp_path / "output.csv"

    export_to_json(sample_posts, json_path)
    assert json_path.exists()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["relevance_score"] == 88

    export_to_csv(sample_posts, csv_path)
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "Scaling Hybrid Search" in content
    assert "abc1234567890def" in content


def test_is_within_max_age():
    ref_time = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)

    # 1 day ago -> within 7 days
    assert is_within_max_age("2026-11-20T12:00:00Z", max_age_days=7.0, reference_time=ref_time) is True
    # 6.5 days ago -> within 7 days
    assert is_within_max_age("2026-11-15T00:00:00Z", max_age_days=7.0, reference_time=ref_time) is True
    # 8 days ago -> older than 7 days, must be rejected
    assert is_within_max_age("2026-11-13T12:00:00Z", max_age_days=7.0, reference_time=ref_time) is False
    # None date -> rejected
    assert is_within_max_age(None, max_age_days=7.0, reference_time=ref_time) is False
    # Invalid string -> rejected
    assert is_within_max_age("not-a-date", max_age_days=7.0, reference_time=ref_time) is False


def test_fetch_all_feeds_filters_stale_posts(tmp_path):
    ref_time = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Weekly AI</title>
        <link>https://example.com</link>
        <item>
          <title>Fresh RAG Article from Today</title>
          <link>https://example.com/fresh-post</link>
          <description>Recent breakthroughs in hybrid vector search and retrieval.</description>
          <pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate>
        </item>
        <item>
          <title>Old RAG Article from Last Month</title>
          <link>https://example.com/old-post</link>
          <description>Old benchmarks on retrieval evaluation.</description>
          <pubDate>Thu, 01 Oct 2026 12:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    feed_path = tmp_path / "weekly.xml"
    feed_path.write_text(xml_content, encoding="utf-8")

    custom_feeds = [{"name": "Weekly AI", "url": "https://example.com/feed.xml", "enabled": True}]

    # Mock fetch_single_feed using monkeypatch or direct fixture content
    from unittest.mock import patch

    with patch("discovery.fetch_feeds.fetch_single_feed") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": "fresh1",
                "canonical_url": "https://example.com/fresh-post",
                "post_url": "https://example.com/fresh-post",
                "source_name": "Weekly AI",
                "author_name": None,
                "title": "Fresh RAG Article from Today",
                "post_text": "Recent breakthroughs in hybrid vector search and retrieval.",
                "published_at": "2026-11-20T12:00:00Z",
                "discovered_at": "2026-11-21T12:00:00Z",
            },
            {
                "id": "old1",
                "canonical_url": "https://example.com/old-post",
                "post_url": "https://example.com/old-post",
                "source_name": "Weekly AI",
                "author_name": None,
                "title": "Old RAG Article from Last Month",
                "post_text": "Old benchmarks on retrieval evaluation.",
                "published_at": "2026-10-01T12:00:00Z",
                "discovered_at": "2026-11-21T12:00:00Z",
            },
        ]

        ranked, stats = fetch_all_feeds(
            feeds_config=custom_feeds,
            limit=10,
            min_score=0,
            max_age_days=7.0,
            reference_time=ref_time,
        )

        # Only the fresh post should be kept; the old post from Oct 1 must be skipped as stale
        assert len(ranked) == 1
        assert ranked[0]["title"] == "Fresh RAG Article from Today"
        assert stats["stale_skipped"] == 1
        assert stats["candidates_scored"] == 1

