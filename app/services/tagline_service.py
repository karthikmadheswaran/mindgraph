"""Weekly inner-state forecast line for the dashboard.

Lazy generate-and-cache: re-runs once per week per user. Cached value lives
in the existing `insights` table under insight_type='weekly_tagline'.
Voice reference: "Mostly reflective this week. Chance of avoidance by Thursday."
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db import supabase
from app.llm import pro as model

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 7
MIN_ENTRIES_FOR_LLM = 3
MAX_WORDS = 14
FALLBACK = "Quiet week. The forecast is whatever you make of it."

# Substring match, case-insensitive. Anything that creeps in here forces a fallback.
BANNED_SUBSTRINGS = (
    "crush it",
    "level up",
    "grind",
    "hustle",
    "honoring",
    "your truth",
    "showing up for yourself",
    "you've got this",
    "youve got this",
    "you got this",
    "manifest",
    "rise and shine",
)


def _try_resolve_zone(user_timezone: Optional[str]):
    """Resolve an IANA tz, falling back to UTC silently. Imported lazily so the
    module is cheap to import in eval contexts."""
    from zoneinfo import ZoneInfo

    try:
        return ZoneInfo(user_timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _fetch_recent_summaries(user_id: str, tz, days: int = 7) -> list[str]:
    """Last N days of completed entry summaries, oldest-first."""
    since = (datetime.now(tz) - timedelta(days=days)).astimezone(timezone.utc).isoformat()
    resp = (
        supabase.table("entries")
        .select("summary, raw_text, created_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .gte("created_at", since)
        .order("created_at", desc=False)
        .execute()
    )
    rows = resp.data or []
    summaries: list[str] = []
    for row in rows:
        summary = (row.get("summary") or "").strip()
        if not summary:
            # Fall back to a short slice of raw_text if the summary node was skipped.
            raw = (row.get("raw_text") or "").strip()
            summary = raw[:200]
        if summary:
            summaries.append(summary)
    return summaries


def _read_cached(user_id: str) -> Optional[dict]:
    resp = (
        supabase.table("insights")
        .select("content, created_at")
        .eq("user_id", user_id)
        .eq("insight_type", "weekly_tagline")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    row = resp.data[0]
    try:
        payload = json.loads(row["content"])
    except Exception:
        return None
    payload["created_at"] = row["created_at"]
    return payload


def _store(user_id: str, text: str) -> None:
    supabase.table("insights").insert(
        {
            "user_id": user_id,
            "insight_type": "weekly_tagline",
            "content": json.dumps({"text": text}),
            "severity": "info",
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


def _cache_is_fresh(cached: dict) -> bool:
    raw = cached.get("created_at")
    if not raw:
        return False
    try:
        gen_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return False
    if gen_at.tzinfo is None:
        gen_at = gen_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - gen_at
    return age < timedelta(days=CACHE_TTL_DAYS)


def validate_tagline(text: str) -> bool:
    """Pure check used by the eval harness AND the runtime guard.

    True  -> output passes all four constraints.
    False -> output is rejected (caller should fall back).
    """
    if not text:
        return False
    cleaned = text.strip()
    if "\n" in cleaned:
        return False
    if "!" in cleaned:
        return False
    if len(cleaned.split()) > MAX_WORDS:
        return False
    lowered = cleaned.lower()
    for banned in BANNED_SUBSTRINGS:
        if banned in lowered:
            return False
    return True


def _build_prompt(summaries: list[str]) -> str:
    joined = "\n".join(f"- {s}" for s in summaries)
    return f"""You are writing a one-line inner-state weather forecast for a user, based on their last 7 days of journal-entry summaries.

VOICE & FORMAT:
- One line. Maximum {MAX_WORDS} words.
- Weather-forecast voice: wry, observational, never judgmental, never motivational.
- Reference style: "Mostly reflective this week. Chance of avoidance by Thursday."
- May name a pattern AND predict a tendency, or just one.

HARD RULES:
- Never tell the user what to do.
- No exclamation marks.
- No motivational verbs (crush it, level up, grind, hustle, manifest).
- No therapy-speak (honoring, your truth, showing up for yourself).

ENTRY SUMMARIES (chronological, last 7 days):
{joined}

Output ONLY the forecast line. No quotes, no preface, no markdown."""


def _strip_wrappers(raw: str) -> str:
    text = raw.strip()
    # Strip surrounding quotes if the model adds them.
    if len(text) >= 2 and text[0] in '"“' and text[-1] in '"”':
        text = text[1:-1].strip()
    # Drop a leading bullet/dash.
    while text.startswith(("-", "*", "•")):
        text = text[1:].lstrip()
    return text


def generate_tagline(summaries: list[str], llm=None) -> str:
    """Pure function: summaries -> tagline. `llm` is injected for tests."""
    if len(summaries) < MIN_ENTRIES_FOR_LLM:
        return FALLBACK
    invoker = llm if llm is not None else model
    try:
        response = invoker.invoke(_build_prompt(summaries))
        raw = getattr(response, "content", str(response))
        text = _strip_wrappers(raw)
    except Exception as exc:
        logger.warning("Tagline LLM call failed: %s", exc)
        return FALLBACK
    if not validate_tagline(text):
        logger.info("Tagline rejected by validator, falling back: %r", text)
        return FALLBACK
    return text


async def get_or_generate_tagline(user_id: str, user_timezone: str = "UTC") -> dict:
    """Lazy-cache the weekly tagline; regenerate if older than CACHE_TTL_DAYS.

    Always returns {"text": str, "cached": bool}.
    """
    cached = _read_cached(user_id)
    if cached and _cache_is_fresh(cached):
        return {"text": cached.get("text") or FALLBACK, "cached": True}

    tz = _try_resolve_zone(user_timezone)
    summaries = _fetch_recent_summaries(user_id, tz, days=7)
    text = generate_tagline(summaries)
    try:
        _store(user_id, text)
    except Exception as exc:
        logger.warning("Failed to store weekly tagline: %s", exc)
    return {"text": text, "cached": False}
