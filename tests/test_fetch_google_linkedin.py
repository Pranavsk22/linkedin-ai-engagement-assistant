"""Unit tests for Google Custom Search LinkedIn discovery."""

import json
from unittest.mock import MagicMock, patch
import pytest

from discovery.fetch_google_linkedin import (
    clean_post_title,
    extract_author_from_title,
    fetch_linkedin_posts_from_google,
)


def test_extract_author_from_title():
    assert extract_author_from_title("Jane Doe on LinkedIn: Evaluating BM25 and vector search") == "Jane Doe"
    assert extract_author_from_title("Dr. Robert Smith, PhD on LinkedIn: New paper on LoRA") == "Dr. Robert Smith, PhD"
    assert extract_author_from_title("Alex Chen - Staff ML Engineer | LinkedIn") == "Alex Chen"
    assert extract_author_from_title("Random LinkedIn Article | LinkedIn") == "Random LinkedIn Article"
    assert extract_author_from_title("") is None
    assert extract_author_from_title(None) is None


def test_clean_post_title():
    t1 = 'Jane Doe on LinkedIn: "Scaling hybrid search in production contracts"'
    assert clean_post_title(t1, "Jane Doe") == "Scaling hybrid search in production contracts"

    t2 = "Vector Search Optimization | LinkedIn"
    assert clean_post_title(t2, None) == "Vector Search Optimization"


def test_fetch_google_linkedin_no_credentials():
    # When no API key or CX is provided, gracefully returns empty list without making HTTP calls
    posts = fetch_linkedin_posts_from_google(api_key="", cx="")
    assert posts == []


def test_fetch_google_linkedin_mocked_response():
    mock_response_data = {
        "items": [
            {
                "link": "https://www.linkedin.com/posts/alice-ml_hybrid-search-activity-7123456789?utm_source=share&trk=feed",
                "title": "Alice ML on LinkedIn: Production RAG evaluation with hybrid BM25 and vector search",
                "snippet": "We evaluated hybrid BM25 and dense retrieval across 5,000 legal contracts and measured latency trade-offs.",
                "pagemap": {
                    "metatags": [
                        {
                            "og:description": "We evaluated hybrid BM25 and dense retrieval across 5,000 legal contracts and measured latency trade-offs.",
                            "article:published_time": "2026-11-20T10:00:00Z",
                        }
                    ]
                },
            },
            {
                # Should be ignored because it is not a /posts/ URL
                "link": "https://www.linkedin.com/in/alice-ml",
                "title": "Alice ML Profile | LinkedIn",
                "snippet": "Profile overview",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data

    with patch("requests.get", return_value=mock_resp):
        posts = fetch_linkedin_posts_from_google(
            api_key="fake-test-key",
            cx="fake-test-cx",
            queries=['site:linkedin.com/posts "RAG"'],
        )

        assert len(posts) == 1
        post = posts[0]
        assert post["source_name"] == "LinkedIn"
        assert post["author_name"] == "Alice ML"
        assert post["canonical_url"] == "https://www.linkedin.com/posts/alice-ml_hybrid-search-activity-7123456789"
        assert "utm_source" not in post["canonical_url"]
        assert "trk" not in post["canonical_url"]
        assert post["relevance_score"] >= 50
        assert "RAG" in json.loads(post["topic_tags"])
        assert post["is_manual_linkedin"] == 1
