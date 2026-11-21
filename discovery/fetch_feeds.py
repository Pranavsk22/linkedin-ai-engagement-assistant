"""Feed fetching, error handling, and cross-feed deduplication."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dateutil import parser as date_parser
import feedparser
import requests

from discovery.normalise import normalise_feed_entry
from discovery.score import load_topics_config, score_post

DEFAULT_FEEDS_PATH = Path(__file__).resolve().parent.parent / "config" / "feeds.json"
DEFAULT_USER_AGENT = "LinkedInAIEngagementAssistant/1.0 (Public Research Collector; +https://github.com/)"

logger = logging.getLogger(__name__)


def load_feeds_config(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load feeds from environment variable RSS_FEEDS or configuration file."""
    env_feeds = os.getenv("RSS_FEEDS", "").strip()
    if env_feeds:
        try:
            # Check if JSON array
            if env_feeds.startswith("["):
                items = json.loads(env_feeds)
                feeds = []
                for idx, item in enumerate(items):
                    if isinstance(item, str):
                        feeds.append({"name": f"Feed {idx + 1}", "url": item, "enabled": True})
                    elif isinstance(item, dict):
                        feeds.append(item)
                return feeds
            else:
                # Comma-separated URLs
                urls = [u.strip() for u in env_feeds.split(",") if u.strip()]
                return [{"name": f"Custom Feed {idx + 1}", "url": u, "enabled": True} for idx, u in enumerate(urls)]
        except Exception as e:
            logger.warning("Failed to parse RSS_FEEDS environment variable (%s). Falling back to file.", e)

    path = config_path or DEFAULT_FEEDS_PATH
    if not path.exists():
        logger.warning("Feeds config file not found: %s", path)
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("feeds", [])


def fetch_single_feed(
    feed_url: str,
    source_name: str,
    timeout: int = 10,
    feed_content: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch and parse a single RSS feed.

    Tolerates network timeouts, HTTP errors, and malformed XML without raising exceptions.
    """
    if feed_content:
        # Use provided content (e.g. for testing / fixtures)
        parsed = feedparser.parse(feed_content)
    else:
        try:
            headers = {"User-Agent": DEFAULT_USER_AGENT}
            response = requests.get(feed_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
        except requests.RequestException as e:
            logger.warning("Failed to fetch feed %s (%s): %s", source_name, feed_url, e)
            return []
        except Exception as e:
            logger.warning("Unexpected error fetching feed %s: %s", source_name, e)
            return []

    if getattr(parsed, "bozo", 0) and not parsed.entries:
        logger.warning("Feed %s produced bozo error and no entries: %s", source_name, getattr(parsed, "bozo_exception", "Unknown"))
        return []

    items = []
    for entry in parsed.entries:
        normalised = normalise_feed_entry(entry, source_name=source_name)
        if normalised:
            items.append(normalised)

    return items


def is_within_max_age(
    published_at: Optional[str],
    max_age_days: float = 7.0,
    reference_time: Optional[datetime] = None,
) -> bool:
    """Return True if published_at is a valid timestamp within max_age_days."""
    if not published_at:
        return False
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
        return False

    ref_dt = reference_time or datetime.now(timezone.utc)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
    else:
        ref_dt = ref_dt.astimezone(timezone.utc)

    delta = (ref_dt - pub_dt).total_seconds()
    if delta < -7200:
        # Future anomaly (> 2 hours in the future)
        return False

    days = max(0.0, delta / 86400.0)
    return days <= max_age_days


def fetch_all_feeds(
    feeds_config: Optional[List[Dict[str, Any]]] = None,
    topics_config: Optional[dict] = None,
    limit: int = 20,
    min_score: int = 0,
    max_age_days: Optional[float] = 7.0,
    reference_time: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Fetch all enabled feeds, deduplicate by canonical URL, score, and rank.

    Only candidates published within max_age_days are retained.

    Returns:
        (ranked_posts, execution_stats)
    """
    feeds = feeds_config if feeds_config is not None else load_feeds_config()
    topics_cfg = topics_config or load_topics_config()

    stats = {
        "feeds_attempted": 0,
        "feeds_successful": 0,
        "total_items_parsed": 0,
        "stale_skipped": 0,
        "duplicates_skipped": 0,
        "candidates_scored": 0,
    }

    # Store posts keyed by canonical_url for deduplication
    posts_by_url: Dict[str, Dict[str, Any]] = {}

    for feed in feeds:
        if not feed.get("enabled", True):
            continue

        url = feed.get("url")
        name = feed.get("name", "Unknown Source")
        if not url:
            continue

        stats["feeds_attempted"] += 1
        items = fetch_single_feed(url, source_name=name)

        if items:
            stats["feeds_successful"] += 1

        for item in items:
            stats["total_items_parsed"] += 1
            canonical_url = item["canonical_url"]

            # Filter out stale items older than max_age_days (within the week)
            if max_age_days is not None:
                if not is_within_max_age(
                    item.get("published_at"),
                    max_age_days=max_age_days,
                    reference_time=reference_time,
                ):
                    stats["stale_skipped"] += 1
                    continue

            # Calculate score for this item
            score, breakdown, matched_topics = score_post(
                title=item["title"],
                text=item["post_text"],
                published_at=item["published_at"],
                config=topics_cfg,
                reference_time=reference_time,
            )

            scored_item = dict(item)
            scored_item["relevance_score"] = score
            scored_item["score_breakdown"] = json.dumps(breakdown)
            scored_item["topic_tags"] = json.dumps(matched_topics)
            scored_item["status"] = "NEW"
            scored_item["is_manual_linkedin"] = 0
            scored_item["created_at"] = item["discovered_at"]
            scored_item["updated_at"] = item["discovered_at"]

            # Deduplication
            if canonical_url in posts_by_url:
                stats["duplicates_skipped"] += 1
                # Retain whichever has the higher score
                if score > posts_by_url[canonical_url]["relevance_score"]:
                    posts_by_url[canonical_url] = scored_item
            else:
                posts_by_url[canonical_url] = scored_item

    # Filter and rank
    all_posts = list(posts_by_url.values())
    if min_score > 0:
        filtered_posts = [p for p in all_posts if p["relevance_score"] >= min_score]
    else:
        filtered_posts = all_posts

    # Sort by relevance_score descending, then published_at descending
    filtered_posts.sort(
        key=lambda p: (
            p["relevance_score"],
            p["published_at"] or "",
        ),
        reverse=True,
    )

    ranked_posts = filtered_posts[:limit]
    stats["candidates_scored"] = len(ranked_posts)

    return ranked_posts, stats
