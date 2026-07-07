# app/services/intention_service.py
"""Read-time drift surfacing (drift P4).

Reads the persisted intentions (written by intention_resolver in store_node and
the P3 backfill) and computes, LIVE per request, how stale each one is:
drift_days = days since last_referenced_at. Nothing is stored — the drift clock
is always "as of now", and the threshold is env-tunable per request so the demo
can be tuned without a redeploy.

Deliberately separate from intention_resolver (the WRITE path); this is the
read-only mirror of deadline_service.list_deadlines.
"""
import logging
import math
import os
import random
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.db import supabase
from app.services.analytics import track
from app.services.helpers import utc_now_iso

logger = logging.getLogger(__name__)

DEFAULT_DRIFT_THRESHOLD_DAYS = 14

# ── Drift pick v1 (single Home card) ──────────────────────────────────────────
PICK_MAX_DAYS = 90          # intentions quiet longer than this are never picked
PICK_COOLDOWN_DAYS = 14     # once surfaced, not re-picked for this long
PICK_STICKY_HOURS = 48      # the same pick is re-served (unstamped) this long
PICK_NEVER_SURFACED_BONUS = 0.5

# Terminal lifecycle statuses (drift P6). SOFT transitions — set status only,
# never deleted_at. Both fall OUTSIDE the active/dormant whitelist that get_drift
# (and the resolver's match query) use, so a resolved/dismissed intention drops
# out of the drift card the moment it's set — read and write stay in lockstep.
RESOLVED = "resolved"
DISMISSED = "dismissed"


def _drift_days(last_referenced_at, now: datetime):
    """Days since last_referenced_at, timezone-aware (mirrors the backfill's
    parse: stored pgvector timestamptz reads back as an ISO string). Returns
    None if the value is missing/unparseable so one bad row never sinks the
    whole response — same per-candidate fail-safe stance as the resolver."""
    if not last_referenced_at:
        return None
    try:
        d = datetime.fromisoformat(str(last_referenced_at).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (now - d).days
    except (ValueError, TypeError) as exc:
        logger.warning(
            "intentions drift: unparseable last_referenced_at %r: %s",
            last_referenced_at,
            exc,
        )
        return None


async def get_drift(user_id: str, threshold_days: int | None = None) -> dict:
    """All live intentions for the user, each tagged with a LIVE drift_days +
    is_drifting (drift_days >= threshold), sorted most-drifted first.

    The threshold is read PER REQUEST from DRIFT_THRESHOLD_DAYS (default 14) so
    it is env-tunable without a restart (kill-switch pattern); an explicit
    threshold_days arg overrides it (lets the demo be tuned per call). Returns
    ALL live rows, not just the drifting ones, so the client decides what to
    show. Domain data only — no card shape (that mapping is P5's job).
    """
    threshold = (
        threshold_days
        if threshold_days is not None
        else int(os.getenv("DRIFT_THRESHOLD_DAYS", str(DEFAULT_DRIFT_THRESHOLD_DAYS)))
    )

    # Mirror the resolver's existing live-intention select (intention_resolver.py),
    # swapping the embedding for the timestamp fields the drift clock needs.
    result = (
        supabase.table("intentions")
        .select("id, text, first_stated_at, last_referenced_at, reference_count, status")
        .eq("user_id", user_id)
        # 'resolved'/'dismissed' (P6) are outside this whitelist, so a closed
        # intention disappears from the card immediately — no separate exclusion.
        .in_("status", ["active", "dormant"])
        .is_("deleted_at", "null")
        .execute()
    )
    rows = result.data or []

    now = datetime.now(timezone.utc)
    items = []
    for r in rows:
        dd = _drift_days(r.get("last_referenced_at"), now)
        items.append(
            {
                "id": r.get("id"),
                "text": r.get("text"),
                "drift_days": dd,
                "is_drifting": dd is not None and dd >= threshold,
                "first_stated_at": r.get("first_stated_at"),
                "last_referenced_at": r.get("last_referenced_at"),
                "reference_count": r.get("reference_count", 1),
                "status": r.get("status"),
            }
        )

    # Most-drifted first; rows whose drift we couldn't compute (None) sink last.
    items.sort(
        key=lambda x: x["drift_days"] if x["drift_days"] is not None else -1,
        reverse=True,
    )
    return {"threshold_days": threshold, "intentions": items}


# ── Self-judgment guard (drift pick v1 — HARD requirement) ────────────────────
# The Home card must NEVER serve an identity-judgment "intention" ("Not be a
# useless guy", "Have an identity") — witnessing those as drift reads as the
# app passing judgment on who the user is. Pick-time filter only: the Journal
# Intentions list still shows every pending row. CONSERVATIVE by design — a
# do-able intention wrongly excluded just never becomes the Home card (small
# cost); a judgment wrongly served violates the product (unacceptable). When
# unsure, exclude.

_SELF_JUDGMENT_PATTERNS = [
    # Negated self-descriptions: "not be a useless guy", "stop being lazy",
    # "quit feeling like this". (Verbs of being/feeling, not of doing —
    # "quit smoking" / "stop procrastinating on X" pass through.)
    re.compile(r"\b(?:not|stop|quit|no longer)\s+(?:be|being|feel|feeling|act|acting)\b", re.I),
    # Worth/adequacy vocabulary anywhere in the text.
    re.compile(r"\b(?:useless|worthless|pathetic|loser|failure|failing|burden|lazy|stupid|weak|broken|a mess)\b", re.I),
    # Identity-seeking: "have an identity", "find myself", "figure out who I am".
    re.compile(r"\bidentity\b", re.I),
    re.compile(r"\b(?:find|figure\s+out|discover)\s+(?:myself|who\s+i\s+am)\b", re.I),
    re.compile(r"\bwho\s+i\s+(?:am|want\s+to\s+be)\b", re.I),
    # Global self-evaluations: "be a better person", "feel normal", "be enough".
    re.compile(r"\b(?:be|being|feel|feeling)\s+(?:an?\s+)?(?:better|good|real|normal|worthy|enough|confident)\b", re.I),
    re.compile(r"\bself[-\s]?(?:worth|esteem|respect|image|hatred|loathing)\b", re.I),
]


def is_self_judgment(text) -> bool:
    """True -> excluded from the Home pick. Falsy/non-string text is excluded
    too (can't verify -> conservative default)."""
    if not text or not isinstance(text, str):
        return True
    return any(p.search(text) for p in _SELF_JUDGMENT_PATTERNS)


# ── Drift pick v1: scoring ─────────────────────────────────────────────────────


def _maturity_band(days: int) -> float:
    """How 'ripe' a drift is for surfacing. Ramps over the first week (too
    fresh to witness), peaks 7-35d (long enough to mean something, recent
    enough to act on), tapers linearly to 0 at the 90d eligibility cap."""
    if days < 7:
        return days / 7.0
    if days <= 35:
        return 1.0
    return max(0.0, 1.0 - (days - 35) / float(PICK_MAX_DAYS - 35))


def _pick_score(reference_count: int, days: int, never_surfaced: bool) -> float:
    """2.0*log2(1+refs) + maturity_band + never-surfaced bonus. Reference count
    dominates (a thing stated 5 times beats any band value) — clustering
    (deferred design) will make that signal truthful; weights are v1 guesses,
    tuned later from the drift_card_served telemetry."""
    score = 2.0 * math.log2(1 + max(reference_count or 1, 1))
    score += _maturity_band(days)
    if never_surfaced:
        score += PICK_NEVER_SURFACED_BONUS
    return score


def _parse_ts(value):
    """Lenient timestamptz parse (same stance as _drift_days): None on junk."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


async def pick_drift(user_id: str, threshold_days: int | None = None) -> dict:
    """Single-pick mode of the drift endpoint: choose THE one drift card Home
    shows. Contract (drift pick v1):

      eligibility: status pending (active/dormant) AND threshold <= days_since
        <= 90 AND (never surfaced OR surfaced > 14d ago) AND not self-judgment
      stickiness:  the most recently surfaced live intention is re-served
        WITHOUT restamping (and without re-logging) for 48h — same pick within
        a calendar day for free; acting on it (resolve/dismiss) rotates
        immediately because the row leaves the live whitelist
      scoring:     2.0*log2(1+reference_count) + maturity_band(days; peak
        7-35d) + 0.5 never-surfaced bonus; tiebreak least-recently-surfaced,
        then random
      serve:       stamp surfaced_at = now() and fire drift_card_served
        (intention_id, score, days_since, reference_count) — once per pick,
        not per render.
    """
    threshold = (
        threshold_days
        if threshold_days is not None
        else int(os.getenv("DRIFT_THRESHOLD_DAYS", str(DEFAULT_DRIFT_THRESHOLD_DAYS)))
    )

    result = (
        supabase.table("intentions")
        .select(
            "id, text, first_stated_at, last_referenced_at, reference_count, status, surfaced_at"
        )
        .eq("user_id", user_id)
        .in_("status", ["active", "dormant"])
        .is_("deleted_at", "null")
        .execute()
    )
    rows = result.data or []

    now = datetime.now(timezone.utc)
    items = []
    for r in rows:
        items.append(
            {
                **r,
                "_days": _drift_days(r.get("last_referenced_at"), now),
                "_surfaced": _parse_ts(r.get("surfaced_at")),
            }
        )

    def _public(item, score):
        return {
            "id": item.get("id"),
            "text": item.get("text"),
            "drift_days": item["_days"],
            "is_drifting": True,
            "first_stated_at": item.get("first_stated_at"),
            "last_referenced_at": item.get("last_referenced_at"),
            "reference_count": item.get("reference_count", 1),
            "status": item.get("status"),
            "score": round(score, 3),
        }

    # 1. Sticky pick: the most recently surfaced live intention, while its 48h
    # window is open. No restamp, no event — one drift_card_served per pick.
    surfaced_items = [i for i in items if i["_surfaced"] is not None]
    if surfaced_items:
        current = max(surfaced_items, key=lambda i: i["_surfaced"])
        if (
            now - current["_surfaced"] < timedelta(hours=PICK_STICKY_HOURS)
            and current["_days"] is not None
            and not is_self_judgment(current.get("text"))
        ):
            score = _pick_score(current.get("reference_count", 1), current["_days"], False)
            return {"threshold_days": threshold, "pick": _public(current, score)}

    # 2. Fresh pick over the eligible pool.
    cooldown = timedelta(days=PICK_COOLDOWN_DAYS)
    eligible = [
        i
        for i in items
        if i["_days"] is not None
        and threshold <= i["_days"] <= PICK_MAX_DAYS
        and (i["_surfaced"] is None or (now - i["_surfaced"]) >= cooldown)
        and not is_self_judgment(i.get("text"))
    ]
    if not eligible:
        return {"threshold_days": threshold, "pick": None}

    scored = []
    for i in eligible:
        score = _pick_score(
            i.get("reference_count", 1), i["_days"], i["_surfaced"] is None
        )
        scored.append((i, score))

    # Highest score wins; ties go to the least recently surfaced (never-surfaced
    # first), then random.
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    winner, win_score = min(
        scored,
        key=lambda pair: (
            -pair[1],
            (pair[0]["_surfaced"] or epoch),
            random.random(),
        ),
    )

    # 3. Serve: stamp + telemetry (fire-and-forget; track never raises).
    try:
        (
            supabase.table("intentions")
            .update({"surfaced_at": utc_now_iso()})
            .eq("id", winner["id"])
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # pragma: no cover - stamp failure must not kill the card
        logger.warning("drift pick: surfaced_at stamp failed for %s: %s", winner["id"], exc)

    track(
        user_id,
        "drift_card_served",
        {
            "intention_id": winner["id"],
            "score": round(win_score, 3),
            "days_since": winner["_days"],
            "reference_count": winner.get("reference_count", 1),
        },
    )

    return {"threshold_days": threshold, "pick": _public(winner, win_score)}


# ── Lifecycle (drift P6): the first USER-triggered writes to intentions ────────


async def _set_terminal_status(user_id: str, intention_id: str, new_status: str) -> dict:
    """Ownership-scoped SOFT transition. The UPDATE is scoped
    WHERE id = ? AND user_id = ? AND deleted_at IS NULL, so another user's id (or
    a missing / soft-deleted row) matches nothing -> a clean 404, never a 500 and
    never a cross-user write. Idempotent: re-resolving an already-resolved
    intention still matches the row and re-sets the same status -> 200, not an
    error. Sets updated_at as the transition timestamp; the status VALUE
    ('resolved' vs 'dismissed') is what keeps the two actions distinguishable for
    analytics. Never touches deleted_at — fully reversible."""
    result = (
        supabase.table("intentions")
        .update({"status": new_status, "updated_at": utc_now_iso()}, returning="representation")
        .eq("id", intention_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Intention not found")

    # Telemetry (backend-side, mirroring entry_submitted): how quiet was the
    # intention when the user acted on it. track() never raises.
    row = result.data[0]
    track(
        user_id,
        f"intention_{new_status}",
        {
            "intention_id": intention_id,
            "days_since": _drift_days(
                row.get("last_referenced_at"), datetime.now(timezone.utc)
            ),
        },
    )
    return {"status": "ok", "intention": row}


async def resolve_intention(user_id: str, intention_id: str) -> dict:
    """Positive close — "I did this / no longer true". status -> 'resolved'."""
    return await _set_terminal_status(user_id, intention_id, RESOLVED)


async def dismiss_intention(user_id: str, intention_id: str) -> dict:
    """"Stop showing me this" — NOT a completion judgment. status -> 'dismissed'.
    Kept distinct from 'resolved' so launch analytics separate real completions
    from bad-extraction / don't-want-shown."""
    return await _set_terminal_status(user_id, intention_id, DISMISSED)
