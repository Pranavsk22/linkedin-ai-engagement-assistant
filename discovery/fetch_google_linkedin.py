"""Discovery module for fetching real, public LinkedIn posts via Google Custom Search API.

Runs 100% cloud-side on scheduled GitHub Actions (even when laptop is off)
with zero LinkedIn account login credentials and zero ban risk.
"""

from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

from discovery.canonicalise import canonicalise_url
from discovery.normalise import generate_post_id, parse_date_to_iso
from discovery.score import load_topics_config, score_post

logger = logging.getLogger(__name__)

GOOGLE_SEARCH_API_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# Curated queries targeting AI engineering, RAG, and fine-tuning discussions on LinkedIn
DEFAULT_LINKEDIN_SEARCH_QUERIES = [
    'site:linkedin.com/posts ("RAG" OR "hybrid search" OR "vector search" OR "BM25")',
    'site:linkedin.com/posts ("LoRA" OR "fine-tuning" OR "speech AI" OR "Whisper")',
    'site:linkedin.com/posts ("AI engineering" OR "LLM evaluation" OR "on-device AI")',
]


def extract_author_from_title(title: str) -> Optional[str]:
    """Extract person or creator name from Google's LinkedIn search result title.

    Examples:
        - "Jane Doe on LinkedIn: We evaluated hybrid search..." -> "Jane Doe"
        - "John Smith - Founder & CEO | LinkedIn" -> "John Smith"
        - "Alex Chen on LinkedIn: Scaling RAG in production" -> "Alex Chen"
    """
    if not title:
        return None

    # Pattern: "... on LinkedIn: ..."
    m1 = re.match(r"^([^:]+?)\s+on\s+LinkedIn\s*:", title, re.IGNORECASE)
    if m1:
        return m1.group(1).strip()

    # Pattern: "... - Title | LinkedIn" or "... | LinkedIn"
    m2 = re.match(r"^([^|\-]+?)(?:\s+[-|]\s+.*)?\s*\|\s*LinkedIn", title, re.IGNORECASE)
    if m2:
        return m2.group(1).strip()

    return None


def clean_post_title(title: str, author_name: Optional[str] = None) -> str:
    """Clean the search result title into a human-readable post title."""
    cleaned = title
    if author_name and "on LinkedIn:" in cleaned:
        parts = cleaned.split("on LinkedIn:", 1)
        if len(parts) > 1 and parts[1].strip():
            cleaned = parts[1].strip().strip('"').strip("'")
    elif "| LinkedIn" in cleaned:
        cleaned = cleaned.replace("| LinkedIn", "").strip()

    if len(cleaned) > 200:
        cleaned = cleaned[:197] + "..."
    return cleaned or "LinkedIn Discussion"


def fetch_linkedin_posts_from_google(
    api_key: Optional[str] = None,
    cx: Optional[str] = None,
    queries: Optional[List[str]] = None,
    max_per_query: int = 5,
    date_restrict: str = "d7",
    topics_config: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Fetch public LinkedIn posts via Google Custom Search JSON API.

    Args:
        api_key: Google Cloud API Key (or env GOOGLE_SEARCH_API_KEY).
        cx: Google Custom Search Engine ID (or env GOOGLE_SEARCH_CX).
        queries: Search queries targeting LinkedIn posts.
        max_per_query: Number of results to request per query (max 10).
        date_restrict: Google date restriction filter ('d7' for past 7 days).
        topics_config: Optional custom topic configuration dictionary.

    Returns:
        List of normalised, scored post dictionaries ready for ingestion.
    """
    key = (api_key or os.getenv("GOOGLE_SEARCH_API_KEY", "")).strip()
    engine_id = (cx or os.getenv("GOOGLE_SEARCH_CX", "")).strip()

    if not key or not engine_id:
        logger.info(
            "Google Search credentials (GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_CX) not configured. "
            "Skipping Google LinkedIn discovery."
        )
        return []

    target_queries = queries or DEFAULT_LINKEDIN_SEARCH_QUERIES
    topics_cfg = topics_config or load_topics_config()
    candidates: List[Dict[str, Any]] = []
    seen_urls = set()

    for query in target_queries:
        params = {
            "key": key,
            "cx": engine_id,
            "q": query,
            "num": min(10, max(1, max_per_query)),
            "dateRestrict": date_restrict,
        }

        try:
            resp = requests.get(GOOGLE_SEARCH_API_ENDPOINT, params=params, timeout=12)
            if resp.status_code == 403:
                logger.warning("Google Custom Search API returned 403 Forbidden. Check your API key or quota.")
                break
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.warning("Failed Google Custom Search query '%s': %s", query, e)
            continue

        items = data.get("items", [])
        for item in items:
            raw_url = item.get("link", "").strip()
            if not raw_url or "linkedin.com/posts" not in raw_url:
                continue

            try:
                canonical_url = canonicalise_url(raw_url)
            except ValueError:
                continue

            if canonical_url in seen_urls:
                continue
            seen_urls.add(canonical_url)

            raw_title = item.get("title", "").strip()
            snippet = item.get("snippet", "").strip()

            pagemap = item.get("pagemap", {})
            metatags = (pagemap.get("metatags") or [{}])[0]

            author = extract_author_from_title(raw_title)
            title = clean_post_title(raw_title, author)

            # Rich text body (prefer og:description if available)
            og_desc = metatags.get("og:description", "").strip()
            post_text = og_desc if len(og_desc) > len(snippet) else snippet
            if not post_text:
                post_text = title

            raw_pub = metatags.get("article:published_time") or metatags.get("datepublished")
            published_at = parse_date_to_iso(raw_pub) if raw_pub else None

            # Score post
            score, breakdown, matched_topics = score_post(
                title=title,
                text=post_text,
                published_at=published_at,
                config=topics_cfg,
            )

            # Add LinkedIn bonus (+10 pts) for being a direct LinkedIn discussion
            score = min(100, score + 10)
            breakdown["total"] = score
            breakdown["linkedin_source_bonus"] = 10

            post_id = generate_post_id(canonical_url)

            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            candidates.append({
                "id": post_id,
                "canonical_url": canonical_url,
                "post_url": raw_url,
                "source_name": "LinkedIn",
                "author_name": author,
                "title": title,
                "post_text": post_text,
                "published_at": published_at or now_iso,
                "discovered_at": now_iso,
                "topic_tags": json.dumps(matched_topics),
                "relevance_score": score,
                "score_breakdown": json.dumps(breakdown),
                "status": "NEW",
                "is_manual_linkedin": 1,
            })

    logger.info("Discovered %d real LinkedIn posts via Google Search.", len(candidates))
    return candidates
