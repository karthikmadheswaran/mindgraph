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
import os
from datetime import datetime, timezone

from app.db import supabase

logger = logging.getLogger(__name__)

DEFAULT_DRIFT_THRESHOLD_DAYS = 14


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
