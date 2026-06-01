import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

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
# Hours are user-local.
# "night" wraps midnight (21:00 → next day 05:00).
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


def _hour_distance(fractional_hour: float, start_hour: int, end_hour: int) -> float:
    """Minimum circular distance from fractional_hour to the [start, end) window."""
    if start_hour < end_hour:
        if start_hour <= fractional_hour < end_hour:
            return 0.0
        dist_to_start = min(
            abs(fractional_hour - start_hour),
            24.0 - abs(fractional_hour - start_hour),
        )
        dist_to_end = min(
            abs(fractional_hour - end_hour),
            24.0 - abs(fractional_hour - end_hour),
        )
        return min(dist_to_start, dist_to_end)
    # Wrap-around window (night = 21:00 → 05:00).
    if fractional_hour >= start_hour or fractional_hour < end_hour:
        return 0.0
    dist_to_start = min(
        abs(fractional_hour - start_hour),
        24.0 - abs(fractional_hour - start_hour),
    )
    dist_to_end = min(
        abs(fractional_hour - end_hour),
        24.0 - abs(fractional_hour - end_hour),
    )
    return min(dist_to_start, dist_to_end)


def _time_of_day_boost(entry_dt_local: datetime, tod_label: Optional[str]) -> float:
    if not tod_label:
        return 1.0
    span = TIME_OF_DAY_RANGES.get(tod_label)
    if span is None:
        return 1.0
    start_h, end_h = span
    h = entry_dt_local.hour + entry_dt_local.minute / 60.0
    if _hour_in_range(entry_dt_local.hour, tod_label):
        return 1.0
    distance = _hour_distance(h, start_h, end_h)
    if distance < 1.0:
        return 0.7
    if distance < 2.0:
        return 0.4
    return 0.1


def _parse_iso_created_at(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _localize_to_user_tz(dt_utc: datetime, user_tz: str) -> datetime:
    """Convert a UTC-aware datetime to the user's local timezone."""
    try:
        zi = ZoneInfo(user_tz)
    except Exception:
        zi = ZoneInfo("UTC")
    return dt_utc.astimezone(zi)


def _user_day_to_utc_bounds(date_iso: str, user_tz: str) -> tuple[str, str]:
    """Convert a user-local date string (YYYY-MM-DD) to UTC start/end bounds.

    When the user says "May 11", they mean May 11 in their timezone.
    For IST (UTC+5:30), that's UTC May 10 18:30 → UTC May 11 18:30.
    """
    try:
        zi = ZoneInfo(user_tz)
    except Exception:
        zi = ZoneInfo("UTC")

    parsed = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed_utc = parsed.astimezone(timezone.utc)

    # If this was already a midnight-in-UTC value from detect_and_parse_time_range,
    # interpret it as midnight in the USER's timezone instead.
    if parsed_utc.hour == 0 and parsed_utc.minute == 0:
        local_midnight = datetime(
            parsed_utc.year, parsed_utc.month, parsed_utc.day,
            tzinfo=zi,
        )
        return _to_iso(local_midnight), _to_iso(local_midnight + timedelta(days=1))

    return date_iso, date_iso


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


def _adjust_range_for_user_tz(time_range: dict, user_tz: str) -> dict:
    """Convert date boundaries from UTC-midnight interpretation to user-tz-midnight.

    detect_and_parse_time_range produces ranges like:
      start = "2025-05-11T00:00:00+00:00"  (midnight UTC)
      end   = "2025-05-12T00:00:00+00:00"

    But the user in IST (UTC+5:30) means May 11 IST = UTC May 10 18:30 → May 11 18:30.
    This function re-interprets those midnight-UTC boundaries as midnight-in-user-tz.
    """
    if user_tz == "UTC":
        return time_range

    try:
        zi = ZoneInfo(user_tz)
    except Exception:
        return time_range

    start_dt = _parse_iso_created_at(time_range["start"])
    end_dt = _parse_iso_created_at(time_range["end"])
    if start_dt is None or end_dt is None:
        return time_range

    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)

    # Only re-interpret if these look like midnight-UTC boundaries (from our
    # detect_and_parse_time_range or _coerce_range). Non-midnight boundaries
    # (e.g. from relative windows like "last 7 days" computed from now()) are
    # already correct in UTC and should not be shifted.
    if start_utc.hour == 0 and start_utc.minute == 0:
        local_start = datetime(
            start_utc.year, start_utc.month, start_utc.day,
            tzinfo=zi,
        )
        adjusted_start = _to_iso(local_start)
    else:
        adjusted_start = time_range["start"]

    if end_utc.hour == 0 and end_utc.minute == 0:
        local_end = datetime(
            end_utc.year, end_utc.month, end_utc.day,
            tzinfo=zi,
        )
        adjusted_end = _to_iso(local_end)
    else:
        adjusted_end = time_range["end"]

    return {"start": adjusted_start, "end": adjusted_end}


async def temporal_retrieval(state: AskState) -> dict:
    if "temporal" not in (state.get("query_types") or []):
        return {}

    now = datetime.now(timezone.utc)
    user_tz = state.get("user_timezone") or "UTC"
    state_time_range = state.get("time_range") or {}
    time_range = _coerce_range(state_time_range, now) or detect_and_parse_time_range(
        state["question"], now
    )
    if not time_range:
        logger.info("temporal_retrieval: no resolvable date range for query=%r", state["question"])
        return {"temporal_has_results": False}

    # Adjust date-range boundaries from UTC-midnight to user-tz-midnight.
    time_range = _adjust_range_for_user_tz(time_range, user_tz)

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
    #   first and dense days don't cut off the earliest entry.
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

    # Soft-ranking by time_of_day boost (replaces the old strict filter).
    # All entries in the date range are fetched; those outside the time-of-day
    # window get a lower boost but are NOT excluded.
    if time_of_day is not None:
        scored = []
        for row in rows:
            dt = _parse_iso_created_at(row["created_at"])
            if dt is None:
                continue
            local_dt = _localize_to_user_tz(dt, user_tz)
            boost = _time_of_day_boost(local_dt, time_of_day)
            scored.append((boost, row))
        # Stable sort by boost descending — within the same boost tier,
        # the DB's created_at ordering (ASC for narrow, DESC for wide)
        # is preserved by Python's stable sort.
        scored.sort(key=lambda pair: -pair[0])
        rows = [row for _boost, row in scored]

    # Final cap — never return more than 10 to keep prompt size predictable.
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
        "temporal_retrieval: %d entries for range %s..%s time_of_day=%s narrow=%s user_tz=%s",
        len(entries),
        time_range["start"],
        time_range["end"],
        time_of_day,
        is_narrow,
        user_tz,
    )
    return {
        "temporal_entries": entries,
        "temporal_has_results": len(entries) > 0,
    }
