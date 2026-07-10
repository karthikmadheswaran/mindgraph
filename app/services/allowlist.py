"""
Invite-only allowlist check (closed demand-test gating).

Membership lives in the `allowed_emails` table (migration 021), admin-managed
via the Supabase dashboard only. The whole table is cached in-process for
CACHE_TTL_SECONDS so adding an invite needs no redeploy and steady-state
requests cost zero DB round-trips.

Failure posture: if the allowlist can't be fetched (table not yet migrated,
transient DB error), we serve the last good cache; with no cache at all we
FAIL OPEN with a loud log — for a trial gate, silently locking out every user
(including the founder) is worse than briefly not gating. Sentry captures the
fetch error either way.
"""
import logging
import time

import sentry_sdk

from app.db import supabase

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

_cache: dict = {"emails": None, "fetched_at": 0.0}


def _fetch_allowed_emails() -> set[str]:
    resp = supabase.table("allowed_emails").select("email").execute()
    return {row["email"].strip().lower() for row in (resp.data or [])}


def is_email_allowed(email: str | None) -> bool:
    if not email:
        return False

    now = time.monotonic()
    if _cache["emails"] is None or (now - _cache["fetched_at"]) >= CACHE_TTL_SECONDS:
        try:
            _cache["emails"] = _fetch_allowed_emails()
            _cache["fetched_at"] = now
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            if _cache["emails"] is None:
                logger.error(
                    "allowlist fetch failed with no cached copy — gate is OPEN: %s", exc
                )
                return True
            # Serve stale until the next TTL window retries the fetch.
            logger.warning("allowlist refresh failed — serving stale cache: %s", exc)
            _cache["fetched_at"] = now

    return email.strip().lower() in _cache["emails"]


def invalidate_cache() -> None:
    """Test hook / manual reset — force a refetch on the next check."""
    _cache["emails"] = None
    _cache["fetched_at"] = 0.0
