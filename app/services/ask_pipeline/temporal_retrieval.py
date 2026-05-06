import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import dateparser

from app.db import supabase
from app.services.ask_pipeline.date_format import format_entry_date
from app.services.ask_pipeline.state import AskState

logger = logging.getLogger(__name__)

_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec",
)
_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES) + r")\b",
    re.IGNORECASE,
)
_RECENT_SIGNALS = ("latest", "most recent", "newest", "recent")

# Explicit relative phrases (regex, days_back_from_today, days_window).
# We resolve windows ourselves rather than trusting dateparser inside sentences,
# which silently fails on phrasings like "what happened last week".
_RELATIVE_WINDOWS: tuple[tuple[re.Pattern, int, int], ...] = (
    (re.compile(r"\byesterday\b"), 1, 2),
    (re.compile(r"\b(today|this morning|this evening)\b"), 0, 1),
    (re.compile(r"\b(last|past|previous)\s+(week|7\s+days)\b"), 7, 7),
    (re.compile(r"\b(this|current)\s+week\b"), 7, 7),
    (re.compile(r"\b(last|past|previous)\s+month\b"), 30, 30),
    (re.compile(r"\b(this|current)\s+month\b"), 30, 30),
    (re.compile(r"\blast\s+(\d{1,3})\s+days?\b"), -1, -1),  # captured below
    (re.compile(r"\bpast\s+few\s+days\b"), 7, 7),
)


def _next_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1)
    return dt.replace(month=dt.month + 1)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def detect_and_parse_time_range(question: str, today: datetime) -> Optional[dict]:
    """Parse a natural-language date range from a question. Returns
    {"start": iso, "end": iso} (end is exclusive) or None."""
    query_lower = question.lower()
    settings = {
        "PREFER_DAY_OF_MONTH": "first",
        "RELATIVE_BASE": today,
        "TIMEZONE": "UTC",
        "RETURN_AS_TIMEZONE_AWARE": True,
    }

    month_match = _MONTH_PATTERN.search(query_lower)
    if month_match:
        parsed = dateparser.parse(month_match.group(0), settings=settings)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            start = parsed.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = _next_month(start)
            return {"start": _to_iso(start), "end": _to_iso(end)}

    last_n = re.search(r"\blast\s+(\d{1,3})\s+days?\b", query_lower)
    if last_n:
        days = max(1, int(last_n.group(1)))
        return {
            "start": _to_iso(today - timedelta(days=days)),
            "end": _to_iso(today + timedelta(days=1)),
        }

    for pattern, days_back, _window in _RELATIVE_WINDOWS:
        if days_back < 0:
            continue
        if pattern.search(query_lower):
            return {
                "start": _to_iso(today - timedelta(days=days_back)),
                "end": _to_iso(today + timedelta(days=1)),
            }

    if any(s in query_lower for s in _RECENT_SIGNALS):
        return {
            "start": _to_iso(today - timedelta(days=14)),
            "end": _to_iso(today + timedelta(days=1)),
        }

    return None


def _coerce_range(time_range: Optional[dict], today: datetime) -> Optional[dict]:
    """Promote {start: 'YYYY-MM-DD', end: 'YYYY-MM-DD'} from the agent into ISO ranges.
    The agent's `end` is treated as inclusive; we bump it to exclusive day boundary."""
    if not time_range:
        return None
    start = time_range.get("start")
    end = time_range.get("end")
    if not start or not end:
        return None
    try:
        start_dt = dateparser.parse(str(start), settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True})
        end_dt = dateparser.parse(str(end), settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True})
    except Exception:
        return None
    if start_dt is None or end_dt is None:
        return None
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    if end_dt <= start_dt or (end_dt - start_dt).days < 1:
        end_dt = end_dt + timedelta(days=1)
    return {"start": _to_iso(start_dt), "end": _to_iso(end_dt)}


async def temporal_retrieval(state: AskState) -> dict:
    if "temporal" not in (state.get("query_types") or []):
        return {}

    now = datetime.now(timezone.utc)
    time_range = _coerce_range(state.get("time_range"), now) or detect_and_parse_time_range(
        state["question"], now
    )
    if not time_range:
        logger.info("temporal_retrieval: no resolvable date range for query=%r", state["question"])
        return {}

    result = (
        supabase.table("entries")
        .select("id, auto_title, summary, raw_text, cleaned_text, created_at")
        .eq("user_id", state["user_id"])
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .gte("created_at", time_range["start"])
        .lt("created_at", time_range["end"])
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )

    rows = result.data or []
    entries = []
    for row in rows:
        entries.append(
            {
                "id": row.get("id"),
                "title": (row.get("auto_title") or "Untitled").strip(),
                "raw_text": (row.get("cleaned_text") or row.get("raw_text") or "").strip(),
                "summary": (row.get("summary") or "").strip(),
                "date": format_entry_date(row["created_at"], now),
                "created_at": row["created_at"],
            }
        )

    logger.info(
        "temporal_retrieval: %d entries for range %s..%s",
        len(entries),
        time_range["start"],
        time_range["end"],
    )
    return {"temporal_entries": entries}
