"""Deterministic relevance scoring rubric for discovered posts.

Rubric (0-100 total):
- Topic relevance (max 30)
- Technical depth (max 25)
- Practical implementation evidence (max 20)
- Discussion opportunity (max 15)
- Recency (max 10)

Score tiers:
- 75-100: High priority
- 55-74: Review
- 0-54: Ignore
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from dateutil import parser as date_parser

DEFAULT_TOPICS_PATH = Path(__file__).resolve().parent.parent / "config" / "topics.json"


def load_topics_config(config_path: Optional[Path] = None) -> dict:
    """Load the topics configuration JSON file."""
    path = config_path or DEFAULT_TOPICS_PATH
    if not path.exists():
        raise FileNotFoundError(f"Topics config not found at: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _match_keywords(text: str, keywords: List[str]) -> Set[str]:
    """Find unique keywords present in text using boundary-safe matching.

    Ensures words like 'rag' do not match inside 'fragile' or 'storage',
    while properly matching terms like 'precision@k' and 'retrieval-augmented generation'.
    """
    if not text or not keywords:
        return set()

    matched: Set[str] = set()
    text_lower = text.lower()

    for kw in keywords:
        kw_clean = kw.strip().lower()
        if not kw_clean:
            continue
        # Boundary safe regex: not preceded or followed by alphanumeric characters
        pattern = r"(?<![a-zA-Z0-9])" + re.escape(kw_clean) + r"(?![a-zA-Z0-9])"
        if re.search(pattern, text_lower):
            matched.add(kw_clean)

    return matched


def calculate_recency_score(
    published_at: Optional[str],
    reference_time: Optional[datetime] = None,
) -> int:
    """Calculate recency score (0-10 points) based on publication date.

    - If missing or unparseable: 0 points.
    - <= 2 days (48 hours): 10 points.
    - <= 7 days: 7 points.
    - <= 14 days: 4 points.
    - <= 30 days: 2 points.
    - > 30 days or future anomaly: 0 points.
    """
    if not published_at:
        return 0

    try:
        if isinstance(published_at, datetime):
            pub_dt = published_at
        else:
            pub_dt = date_parser.parse(str(published_at).strip())

        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        else:
            pub_dt = pub_dt.astimezone(timezone.utc)
    except Exception:
        return 0

    ref_dt = reference_time or datetime.now(timezone.utc)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
    else:
        ref_dt = ref_dt.astimezone(timezone.utc)

    delta = (ref_dt - pub_dt).total_seconds()
    if delta < 0:
        # Date is in the future
        return 0

    days = delta / 86400.0

    if days <= 2.0:
        return 10
    if days <= 7.0:
        return 7
    if days <= 14.0:
        return 4
    if days <= 30.0:
        return 2
    return 0


def score_post(
    title: str,
    text: str,
    published_at: Optional[str],
    config: Optional[dict] = None,
    reference_time: Optional[datetime] = None,
) -> Tuple[int, Dict[str, Any], List[str]]:
    """Calculate deterministic relevance score and explainable breakdown.

    Returns:
        (total_score, score_breakdown, matched_topic_names)
    """
    cfg = config or load_topics_config()
    combined_text = f"{title}\n{text}"

    # 1. Topic Relevance (max 30)
    matched_topics: List[str] = []
    matched_topic_keywords: Set[str] = set()
    raw_topic_points = 0.0

    for topic in cfg.get("topics", []):
        t_name = topic.get("name", "Unknown")
        priority = float(topic.get("priority", 10)) / 10.0
        keywords = topic.get("keywords", [])

        title_matches = _match_keywords(title, keywords)
        text_matches = _match_keywords(text, keywords)
        all_topic_matches = title_matches.union(text_matches)

        if all_topic_matches:
            matched_topics.append(t_name)
            matched_topic_keywords.update(all_topic_matches)
            # Title matches receive higher weight
            topic_pts = (len(title_matches) * 8.0 + len(text_matches - title_matches) * 5.0) * priority
            raw_topic_points += topic_pts

    topic_relevance_score = min(30, int(round(raw_topic_points)))

    # 2. Technical Depth (max 25)
    tech_keywords = cfg.get("technical_depth_keywords", [])
    matched_tech = _match_keywords(combined_text, tech_keywords)
    # 4 points per unique matched technical indicator
    technical_depth_score = min(25, len(matched_tech) * 4)

    # 3. Practical Implementation Evidence (max 20)
    impl_keywords = cfg.get("implementation_keywords", [])
    matched_impl = _match_keywords(combined_text, impl_keywords)
    # 4 points per unique matched implementation indicator
    implementation_score = min(20, len(matched_impl) * 4)

    # 4. Discussion Opportunity (max 15)
    disc_keywords = cfg.get("discussion_keywords", [])
    matched_disc = _match_keywords(combined_text, disc_keywords)
    has_question = "?" in combined_text
    disc_pts = (len(matched_disc) * 3) + (5 if has_question else 0)
    discussion_score = min(15, disc_pts)

    # 5. Recency (max 10)
    recency_score = calculate_recency_score(published_at, reference_time=reference_time)

    # Total score calculation
    raw_total = topic_relevance_score + technical_depth_score + implementation_score + discussion_score + recency_score

    # Hard filter: if no relevant topics matched, the post should be ignored
    if not matched_topics:
        total_score = min(30, raw_total // 2)
    else:
        total_score = max(0, min(100, raw_total))

    # Classification
    if total_score >= 75:
        category = "High priority"
    elif total_score >= 55:
        category = "Review"
    else:
        category = "Ignore"

    breakdown = {
        "total": total_score,
        "category": category,
        "topic_relevance": topic_relevance_score,
        "technical_depth": technical_depth_score,
        "practical_implementation": implementation_score,
        "discussion_opportunity": discussion_score,
        "recency": recency_score,
        "matched_topics": matched_topics,
        "matched_topic_keywords": sorted(list(matched_topic_keywords)),
        "matched_technical_terms": sorted(list(matched_tech)),
        "matched_implementation_terms": sorted(list(matched_impl)),
        "matched_discussion_terms": sorted(list(matched_disc)),
        "has_question": has_question,
    }

    return total_score, breakdown, matched_topics
