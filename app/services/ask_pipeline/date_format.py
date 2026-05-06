from datetime import datetime, timezone


def _parse_iso(timestamp: str | datetime) -> datetime:
    if isinstance(timestamp, datetime):
        dt = timestamp
    else:
        dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_entry_date(timestamp: str | datetime, now: datetime | None = None) -> str:
    """Format a timestamp as 'Tuesday, May 05, 2026 (yesterday)' style."""
    dt = _parse_iso(timestamp)
    now = now or datetime.now(timezone.utc)
    days_ago = (now.date() - dt.date()).days

    if days_ago <= 0:
        relative = "today"
    elif days_ago == 1:
        relative = "yesterday"
    elif days_ago < 7:
        relative = f"{days_ago} days ago"
    elif days_ago < 30:
        weeks = days_ago // 7
        relative = f"{weeks} week{'s' if weeks > 1 else ''} ago"
    else:
        relative = f"{days_ago} days ago"

    return f"{dt.strftime('%A, %B %d, %Y')} ({relative})"


def today_str(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%A, %B %d, %Y")
