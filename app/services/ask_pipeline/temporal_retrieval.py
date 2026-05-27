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
# Day-aware match: "may 11", "May 11th", "Jan 3rd" — preferred over bare month
# so that questions like "morning of May 11th" don't degrade to a whole-month
# range. See the May 11th regression filed 27/05/2026 for context.
_MONTH_DAY_PATTERN = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)
# Bare-month fallback. Only consulted if no _MONTH_DAY_PATTERN match exists.
_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES) + r")\b",
    re.IGNORECASE,
)
_RECENT_SIGNALS = ("latest", "most recent", "newest", "recent")

# Canonical time-of-day hour ranges. Half-open intervals [start, end).
# Hours are user-local; "night" wraps midnight (21:00 → next day 05:00).
# NOTE: AskState does not currently carry user_timezone (see TODO in
# `temporal_retrieval` below). When the user's timezone is unknown, these
# ranges are applied against the entry's UTC hour. For users in IST that
# means a 5.5h shift — a known imprecision tracked as Layer 3 work
# (referenced-date indexing) in the Status Hub roadmap.
TIME_OF_DAY_RANGES: dict[str, tuple[int, int]] = {
    "morning":   (5, 12),
    "afternoon": (12, 17),
    "evening":   (17, 21),
    "night":     (21, 5),   # wraps midnight; handled specially in _hour_in_range
}

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


def _hour_in_range(hour: int, time_of_day: str) -> bool:
    """Apply a canonical time-of-day window. `night` wraps midnight."""
    span = TIME_OF_DAY_RANGES.get(time_of_day)
    if span is None:
        return True
    start_hour, end_hour = span
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    # Wrap-around (night = 21:00 → 05:00 next day).
    return hour >= start_hour or hour < end_hour


def _parse_iso_created_at(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def detect_and_parse_time_range(question: str, today: datetime) -> Optional[dict]:
    """Parse a natural-language date range from a question. Returns
    {"start": iso, "end": iso} (end is exclusive) or None.

    Prefers month+day matches (e.g. "May 11th") over bare-month matches
    (e.g. "may") so that "morning of May 11th" doesn't degrade to a
    whole-month range."""
    query_lower = question.lower()
    settings = {
        "PREFER_DAY_OF_MONTH": "first",
        "RELATIVE_BASE": today,
        "TIMEZONE": "UTC",
        "RETURN_AS_TIMEZONE_AWARE": True,
    }

    # 1) Day-specific match wins: "May 11th" → one-day window starting May 11.
    day_match = _MONTH_DAY_PATTERN.search(query_lower)
    if day_match:
        parsed = dateparser.parse(
            f"{day_match.group(1)} {day_match.group(2)}",
            settings=settings,
        )
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            start = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            return {"start": _to_iso(start), "end": _to_iso(end)}

    # 2) Bare-month fallback (whole-month range).
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


def _is_narrow_range(start_iso: str, end_iso: str) -> bool:
    """A `narrow` range spans ≤ 24h — typically a single-day query."""
    start_dt = _parse_iso_created_at(start_iso)
    end_dt = _parse_iso_created_at(end_iso)
    if start_dt is None or end_dt is None:
        return False
    return (end_dt - start_dt) <= timedelta(hours=24)


async def temporal_retrieval(state: AskState) -> dict:
    if "temporal" not in (state.get("query_types") or []):
        return {}

    now = datetime.now(timezone.utc)
    state_time_range = state.get("time_range") or {}
    time_range = _coerce_range(state_time_range, now) or detect_and_parse_time_range(
        state["question"], now
    )
    if not time_range:
        logger.info("temporal_retrieval: no resolvable date range for query=%r", state["question"])
        return {"temporal_has_results": False}

    # Pull `time_of_day` from the agent's time_range (if it set one). Only
    # canonical labels reach this point — query_agent._parse_agent_json drops
    # non-canonical values.
    time_of_day: Optional[str] = None
    if isinstance(state_time_range, dict):
        tod_candidate = state_time_range.get("time_of_day")
        if tod_candidate in TIME_OF_DAY_RANGES:
            time_of_day = tod_candidate

    # LIMIT/ORDER strategy:
    # - Narrow single-day range: ASC + LIMIT 25 so morning entries surface
    #   first and dense days (the test user wrote 13 entries on May 11) don't
    #   cut off the earliest entry. If time_of_day is set we Python-filter
    #   below; LIMIT 25 leaves enough headroom for the filter.
    # - Multi-day range: keep DESC (recent first) + LIMIT 10. If time_of_day
    #   is set on a multi-day range, bump to LIMIT 50 so the post-filter has
    #   enough candidates to work with.
    is_narrow = _is_narrow_range(time_range["start"], time_range["end"])
    if is_narrow:
        query_limit = 25
        order_desc = False  # ASC: morning first
    else:
        query_limit = 50 if time_of_day else 10
        order_desc = True   # DESC: recent first

    # TODO(Layer 2 timezone): AskState does not currently carry user_timezone,
    # so EXTRACT(HOUR ...) is implicitly UTC. For users not in UTC the
    # canonical "morning" window is offset from the user's perceived morning.
    # See Layer 3 referenced-date indexing roadmap in Status Hub for the
    # proper fix (which also subsumes content-vs-created_at mismatches).
    result = (
        supabase.table("entries")
        .select("id, auto_title, summary, raw_text, cleaned_text, created_at")
        .eq("user_id", state["user_id"])
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .gte("created_at", time_range["start"])
        .lt("created_at", time_range["end"])
        .order("created_at", desc=order_desc)
        .limit(query_limit)
        .execute()
    )

    rows = result.data or []

    # Apply time-of-day Python-filter if requested. We over-fetched above so
    # this can produce a smaller-but-still-useful result without a second
    # roundtrip. SQL-side EXTRACT(HOUR …) was considered and rejected: it
    # requires PostgREST expression filters or a new RPC, neither of which
    # earns its keep for a 25-row post-filter.
    if time_of_day is not None:
        filtered = []
        for row in rows:
            dt = _parse_iso_created_at(row["created_at"])
            if dt is None:
                continue
            if _hour_in_range(dt.astimezone(timezone.utc).hour, time_of_day):
                filtered.append(row)
        rows = filtered

    # Final cap — never return more than 10 narrow / 10 broad to keep prompt
    # size predictable. The fetch-then-filter dance only widened the candidate
    # pool; the user-visible result is still bounded.
    rows = rows[:10]

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
        "temporal_retrieval: %d entries for range %s..%s time_of_day=%s narrow=%s",
        len(entries),
        time_range["start"],
        time_range["end"],
        time_of_day,
        is_narrow,
    )
    return {
        "temporal_entries": entries,
        "temporal_has_results": len(entries) > 0,
    }
