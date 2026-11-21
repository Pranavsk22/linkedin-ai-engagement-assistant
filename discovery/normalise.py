"""HTML stripping, date parsing, and feed entry normalisation."""

import hashlib
import html
import re
import warnings
from datetime import datetime, timezone
from typing import Any, Optional
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from dateutil import parser as date_parser

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

from discovery.canonicalise import canonicalise_url, is_valid_url


def strip_html(html_content: str) -> str:
    """Safely extract plain text from an HTML string.

    Removes script, style, iframe elements, decodes HTML entities,
    and normalises whitespace.
    """
    if not html_content or not isinstance(html_content, str):
        return ""

    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
    except Exception:
        # Fallback regex strip if BeautifulSoup fails
        text = re.sub(r"<[^>]+>", " ", html_content)

    # Decode HTML entities
    text = html.unescape(text)
    # Collapse multiple whitespaces/newlines into clean text
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date_to_iso(date_input: Any) -> Optional[str]:
    """Parse various date formats into standard UTC ISO 8601 string.

    Returns string formatted as 'YYYY-MM-DDTHH:MM:SSZ' or None if invalid.
    """
    if not date_input:
        return None

    # Handle feedparser struct_time
    if hasattr(date_input, "tm_year"):
        try:
            dt = datetime(
                year=date_input.tm_year,
                month=date_input.tm_mon,
                day=date_input.tm_mday,
                hour=date_input.tm_hour,
                minute=date_input.tm_min,
                second=date_input.tm_sec,
                tzinfo=timezone.utc,
            )
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None

    if isinstance(date_input, datetime):
        if date_input.tzinfo is None:
            date_input = date_input.replace(tzinfo=timezone.utc)
        else:
            date_input = date_input.astimezone(timezone.utc)
        return date_input.strftime("%Y-%m-%dT%H:%M:%SZ")

    if isinstance(date_input, str):
        date_str = date_input.strip()
        if not date_str:
            return None
        try:
            parsed_dt = date_parser.parse(date_str)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            else:
                parsed_dt = parsed_dt.astimezone(timezone.utc)
            return parsed_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None

    return None


def generate_post_id(canonical_url: str) -> str:
    """Generate a deterministic 16-character hex ID from a canonical URL."""
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


def normalise_feed_entry(
    entry: dict,
    source_name: str,
    max_text_length: int = 8000,
    discovery_time: Optional[datetime] = None,
) -> Optional[dict]:
    """Normalise an RSS feed item into a structured post dictionary.

    Returns None if the item lacks a usable URL, title, or body text.
    """
    # Extract raw URL
    raw_url = entry.get("link") or entry.get("id") or ""
    if not is_valid_url(raw_url):
        return None

    try:
        clean_url = canonicalise_url(raw_url)
    except Exception:
        return None

    # Extract title
    raw_title = entry.get("title") or ""
    clean_title = strip_html(raw_title)
    if not clean_title:
        return None

    # Extract post text / summary
    raw_content = ""
    # Check feedparser content blocks
    if "content" in entry and isinstance(entry["content"], list) and len(entry["content"]) > 0:
        raw_content = entry["content"][0].get("value", "")
    elif "summary" in entry and entry["summary"]:
        raw_content = entry["summary"]
    elif "description" in entry and entry["description"]:
        raw_content = entry["description"]

    clean_text = strip_html(raw_content)
    # If content was empty or very short, use clean title as text
    if not clean_text:
        clean_text = clean_title

    # Truncate summary to max_text_length
    if len(clean_text) > max_text_length:
        clean_text = clean_text[:max_text_length]

    # Extract author
    author = entry.get("author") or ""
    if isinstance(author, dict):
        author = author.get("name", "")
    author = strip_html(str(author)) or None

    # Publication date
    pub_input = entry.get("published_parsed") or entry.get("updated_parsed") or entry.get("published") or entry.get("updated")
    published_at = parse_date_to_iso(pub_input)

    # Discovered timestamp
    disc_dt = discovery_time or datetime.now(timezone.utc)
    discovered_at = disc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    post_id = generate_post_id(clean_url)

    return {
        "id": post_id,
        "canonical_url": clean_url,
        "post_url": raw_url.strip(),
        "source_name": source_name,
        "author_name": author,
        "title": clean_title,
        "post_text": clean_text,
        "published_at": published_at,
        "discovered_at": discovered_at,
    }
