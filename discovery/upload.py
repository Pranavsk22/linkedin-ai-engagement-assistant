"""CLI runner and upload orchestrator for scheduled feed discovery.

Supports local JSON/CSV export for Milestone 1 development and authenticated
cloud ingestion for later milestones.
"""

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional
import requests

from discovery.fetch_feeds import fetch_all_feeds
from discovery.fetch_google_linkedin import fetch_linkedin_posts_from_google

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("discovery.upload")


def export_to_json(posts: List[dict], output_path: Path) -> None:
    """Save discovered posts to a formatted JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)
    logger.info("Exported %d posts to JSON: %s", len(posts), output_path)


def export_to_csv(posts: List[dict], output_path: Path) -> None:
    """Save discovered posts to a human-readable CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "relevance_score",
        "topic_tags",
        "title",
        "source_name",
        "author_name",
        "canonical_url",
        "published_at",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for p in posts:
            writer.writerow(p)
    logger.info("Exported %d posts to CSV: %s", len(posts), output_path)


def upload_to_cloud(posts: List[dict], ingest_url: str, bearer_token: str) -> bool:
    """Send authenticated ingestion payload to Cloudflare Worker."""
    if not posts:
        logger.info("No posts to upload.")
        return True

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "User-Agent": "LinkedInAIEngagementAssistant/1.0",
    }
    payload = {"posts": posts}

    try:
        response = requests.post(ingest_url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            logger.info("Successfully ingested %d posts to cloud backend.", len(posts))
            return True
        elif response.status_code == 401:
            logger.error("Cloud ingestion failed: Unauthorized (HTTP 401). Check INGEST_BEARER_TOKEN.")
            return False
        else:
            logger.error("Cloud ingestion failed with status %d: %s", response.status_code, response.text)
            return False
    except requests.RequestException as e:
        logger.error("Cloud ingestion network error: %s", e)
        return False


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="LinkedIn AI Engagement Assistant - Discovery Engine")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of candidate posts to produce (default: 20)")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum score threshold (e.g. 55 for review queue)")
    parser.add_argument("--max-age-days", type=float, default=7.0, help="Maximum age of candidate posts in days (default: 7.0 for within the same week)")
    parser.add_argument("--output-json", type=str, default="", help="Path to save results as JSON")
    parser.add_argument("--output-csv", type=str, default="", help="Path to save results as CSV")
    parser.add_argument("--local-only", action="store_true", help="Force local mode, skipping cloud upload even if credentials exist")

    args = parser.parse_args(argv)

    logger.info("Starting feed discovery job (limit=%d, min_score=%d, max_age_days=%.1f)...", args.limit, args.min_score, args.max_age_days)
    posts, stats = fetch_all_feeds(limit=args.limit, min_score=args.min_score, max_age_days=args.max_age_days)

    # Attempt Google Search discovery for real, direct LinkedIn posts
    linkedin_posts = fetch_linkedin_posts_from_google()
    if linkedin_posts:
        combined_by_url = {p["canonical_url"]: p for p in posts}
        for lp in linkedin_posts:
            if lp["canonical_url"] not in combined_by_url or lp["relevance_score"] > combined_by_url[lp["canonical_url"]]["relevance_score"]:
                combined_by_url[lp["canonical_url"]] = lp

        all_combined = list(combined_by_url.values())
        if args.min_score > 0:
            all_combined = [p for p in all_combined if p["relevance_score"] >= args.min_score]
        all_combined.sort(key=lambda p: (p["relevance_score"], p.get("published_at") or ""), reverse=True)
        posts = all_combined[:args.limit]
        stats["linkedin_posts_discovered"] = len(linkedin_posts)
        stats["candidates_scored"] = len(posts)

    print("\n" + "=" * 50)
    print("DISCOVERY JOB EXECUTION SUMMARY")
    print("=" * 50)
    print(f"Feeds attempted:       {stats['feeds_attempted']}")
    print(f"Feeds successful:      {stats['feeds_successful']}")
    print(f"Total items parsed:    {stats['total_items_parsed']}")
    print(f"Stale items skipped:   {stats.get('stale_skipped', 0)}")
    if "linkedin_posts_discovered" in stats:
        print(f"LinkedIn posts added:  {stats['linkedin_posts_discovered']}")
    print(f"Duplicates skipped:    {stats['duplicates_skipped']}")
    print(f"Ranked candidates:     {stats['candidates_scored']}")
    print("=" * 50 + "\n")

    if args.output_json:
        export_to_json(posts, Path(args.output_json))

    if args.output_csv:
        export_to_csv(posts, Path(args.output_csv))

    ingest_url = os.getenv("INGEST_URL", "").strip()
    ingest_token = os.getenv("INGEST_BEARER_TOKEN", "").strip()

    if ingest_url and ingest_token and not args.local_only:
        logger.info("Uploading %d posts to cloud backend at %s", len(posts), ingest_url)
        success = upload_to_cloud(posts, ingest_url, ingest_token)
        return 0 if success else 1
    else:
        logger.info("Local run completed successfully (no cloud upload requested).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
