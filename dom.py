from datetime import datetime, timezone, timedelta
import re

# Taipei timezone (UTC+8)
TAIPEI_TZ = timezone(timedelta(hours=8))


def extract_text(node, selector: str) -> str:
    """Extract text from a node using CSS selector.

    Args:
        node: HTML node to search within
        selector: CSS selector string

    Returns:
        Extracted text or empty string if not found
    """
    target = node.css_first(selector)
    if target is None:
        return ""
    text = target.text(strip=True)
    return text or ""


def extract_datetime(node, selector: str) -> datetime | None:
    """Extract datetime from a node, checking datetime/content attributes.

    Tries to extract datetime from:
    1. datetime attribute (for <time> tags)
    2. content attribute (for meta tags)
    3. text content

    Supports multiple datetime formats:
    - ISO 8601 (with or without timezone)
    - YYYY-MM-DD HH:MM:SS
    - YYYY-MM-DD
    - Chinese format: 12月06週六202517:12 (month day weekday year hour:minute)

    Args:
        node: HTML node to search within
        selector: CSS selector string

    Returns:
        Parsed datetime object or None if not found/parseable
    """
    target = node.css_first(selector)
    if target is None:
        return None

    # Try datetime attribute
    dt_str = target.attributes.get("datetime")
    if not dt_str:
        # Try content attribute
        dt_str = target.attributes.get("content")
    if not dt_str:
        # Fall back to text
        dt_str = target.text(strip=True)

    if not dt_str:
        return None

    # Parse datetime string (supports ISO 8601 format)
    try:
        # Try parsing with timezone
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        # Try other common formats if needed
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(dt_str, "%Y-%m-%d")
            except ValueError:
                # Try Chinese format: 12月06週六202517:12
                # Pattern: <month>月<day>週<weekday><year><hour>:<minute>
                # Note: All dates from this crawler are in Taipei timezone (UTC+8)
                match = re.match(r"(\d+)月(\d+)週.(\d{4})(\d{2}):(\d{2})", dt_str)
                if match:
                    month, day, year, hour, minute = match.groups()
                    try:
                        return datetime(year=int(year), month=int(month), day=int(day), hour=int(hour), minute=int(minute), tzinfo=TAIPEI_TZ)
                    except ValueError:
                        return None
                return None


def extract_url(node, selector: str) -> str | None:
    """Extract URL from a node's href attribute.

    Args:
        node: HTML node to search within
        selector: CSS selector string

    Returns:
        URL string or None if not found
    """
    target = node.css_first(selector)
    if target is None:
        return None

    href = target.attributes.get("href")
    if not href:
        return None

    return href
