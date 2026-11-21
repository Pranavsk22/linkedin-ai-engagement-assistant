"""Unit tests for deterministic post relevance scoring."""

from datetime import datetime, timezone
import pytest
from discovery.score import calculate_recency_score, score_post


@pytest.fixture
def test_config():
    return {
        "topics": [
            {
                "name": "RAG",
                "priority": 10,
                "keywords": ["rag", "hybrid search", "bm25", "vector search", "reranking"]
            },
            {
                "name": "AI Engineering",
                "priority": 10,
                "keywords": ["production ai", "llm applications", "deployment", "observability"]
            },
            {
                "name": "LLM Evaluation",
                "priority": 10,
                "keywords": ["evaluation", "ragas", "faithfulness", "precision@k"]
            }
        ],
        "technical_depth_keywords": [
            "architecture", "evaluation", "benchmark", "latency", "trade-off", "precision", "observability"
        ],
        "implementation_keywords": [
            "built", "deployed", "measured", "tested", "implemented", "production", "case study"
        ],
        "discussion_keywords": [
            "limitation", "trade-off", "lessons learned", "challenge", "question"
        ]
    }


def test_score_high_priority_post(test_config):
    ref_time = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    title = "Deploying Production RAG: Hybrid Search with BM25 and Vector Search"
    text = (
        "We built and tested a production AI system combining BM25 and vector search. "
        "We measured latency and evaluation metrics with precision@k benchmarks. "
        "What are the architecture trade-offs and key limitations you face?"
    )
    pub_date = "2026-11-20T10:00:00Z"  # 1 day ago -> 10 recency points

    score, breakdown, matched_topics = score_post(
        title=title,
        text=text,
        published_at=pub_date,
        config=test_config,
        reference_time=ref_time,
    )

    assert score >= 75
    assert breakdown["category"] == "High priority"
    assert "RAG" in matched_topics
    assert breakdown["recency"] == 10
    assert breakdown["has_question"] is True
    assert 0 <= score <= 100


def test_score_boundary_safe_keyword_matching(test_config):
    """Ensure 'rag' does not match inside 'courage', 'storage', or 'fragile'."""
    title = "Storage solutions and courage in engineering"
    text = "We faced a fragile situation without any retrieval systems."
    pub_date = "2026-11-20T10:00:00Z"

    score, breakdown, matched_topics = score_post(
        title=title,
        text=text,
        published_at=pub_date,
        config=test_config,
    )

    # Neither RAG nor any other topic should be matched
    assert "RAG" not in matched_topics
    assert breakdown["topic_relevance"] == 0
    assert breakdown["category"] == "Ignore"


def test_score_keyword_deduplication(test_config):
    """Repeatedly mentioning 'rag' should not count multiple times in the same field."""
    title = "RAG RAG RAG RAG RAG"
    text = "RAG is RAG and RAG."

    score1, b1, _ = score_post(title=title, text=text, published_at=None, config=test_config)
    score2, b2, _ = score_post(title="RAG", text="RAG", published_at=None, config=test_config)

    assert b1["topic_relevance"] == b2["topic_relevance"]


def test_score_case_insensitivity(test_config):
    title_lower = "bm25 hybrid search and deployment"
    title_upper = "BM25 HYBRID SEARCH AND DEPLOYMENT"

    s1, _, _ = score_post(title=title_lower, text="", published_at=None, config=test_config)
    s2, _, _ = score_post(title=title_upper, text="", published_at=None, config=test_config)

    assert s1 == s2


def test_recency_score_decay():
    ref_time = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)

    # 1 day old -> 10 pts
    assert calculate_recency_score("2026-11-20T10:00:00Z", reference_time=ref_time) == 10
    # 5 days old -> 7 pts
    assert calculate_recency_score("2026-11-16T10:00:00Z", reference_time=ref_time) == 7
    # 10 days old -> 4 pts
    assert calculate_recency_score("2026-11-11T10:00:00Z", reference_time=ref_time) == 4
    # 25 days old -> 2 pts
    assert calculate_recency_score("2026-10-27T10:00:00Z", reference_time=ref_time) == 2
    # 60 days old -> 0 pts
    assert calculate_recency_score("2026-09-20T10:00:00Z", reference_time=ref_time) == 0
    # Missing date -> 0 pts
    assert calculate_recency_score(None, reference_time=ref_time) == 0
    # Malformed date -> 0 pts
    assert calculate_recency_score("broken-date-xyz", reference_time=ref_time) == 0


def test_irrelevant_post_scored_as_ignore(test_config):
    title = "Best Homemade Apple Pie Recipe"
    text = "Mix cinnamon, sugar, and sliced apples into a flaky butter crust."

    score, breakdown, matched_topics = score_post(
        title=title,
        text=text,
        published_at="2026-11-20T10:00:00Z",
        config=test_config,
    )

    assert score < 55
    assert breakdown["category"] == "Ignore"
    assert len(matched_topics) == 0
