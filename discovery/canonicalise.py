"""URL canonicalisation and cleaning utility.

Removes marketing/analytics tracking parameters and hash fragments while
preserving essential resource identifiers and path structure.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "_gl",
    "ref",
    "ref_src",
    "source",
    "feature",
    "trackingId",
    "trackingid",
    "trk",
    "rcm",
    "originalSubdomain",
}


def is_valid_url(url: str) -> bool:
    """Check if the provided string is a valid HTTP or HTTPS URL."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url.strip())
        return parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def canonicalise_url(url: str) -> str:
    """Canonicalise a URL for stable deduplication.

    - Verifies scheme (http/https).
    - Lowercases scheme and netloc.
    - Strips hash fragments (#).
    - Filters out common tracking/analytics query parameters.
    - Preserves functional query parameters in sorted order.
    - Normalises double slashes in paths.
    """
    if not is_valid_url(url):
        raise ValueError(f"Invalid URL: {url}")

    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Normalise port if default
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Normalise path: collapse multiple slashes
    path = re.sub(r"/{2,}", "/", parsed.path)
    if not path:
        path = "/"
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Filter and sort query parameters
    query_params = parse_qsl(parsed.query, keep_blank_values=False)
    filtered_params = [
        (k, v)
        for k, v in query_params
        if k.lower() not in TRACKING_QUERY_PARAMS
    ]
    # Sort for deterministic representation
    filtered_params.sort(key=lambda item: (item[0], item[1]))
    new_query = urlencode(filtered_params)

    # Omit fragment
    return urlunsplit((scheme, netloc, path, new_query, ""))
