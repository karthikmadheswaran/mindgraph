"""
Invite-access request intake (access_requests table, migration 023).

Strangers who hit the invite gate can leave an email + optional note here.
Granting is manual: Karthik copies the email into `allowed_emails` via the
Supabase dashboard (see docs/request-access.md).

Failure/enumeration posture:
  * Duplicate email (unique index on lower(email)) → swallow the conflict and
    report success. Callers must never learn whether an email was already on
    file (no account/interest enumeration).
  * Table absent (migration 023 not yet applied on prod) → log loudly to
    Sentry and still report success, so the UI doesn't surface an error during
    the deploy→dashboard-apply window. Same fail-safe spirit as the allowlist.
"""
import logging

import sentry_sdk

from app.db import supabase

logger = logging.getLogger(__name__)

NOTE_MAX_LEN = 280

# PostgREST/Postgres codes we treat as "already recorded" — idempotent success.
_DUPLICATE_MARKERS = ("23505", "duplicate key", "idx_access_requests_email_lower")


def submit_access_request(email: str, note: str | None) -> None:
    payload = {"email": email.strip().lower()}
    if note:
        payload["note"] = note.strip()[:NOTE_MAX_LEN]

    try:
        supabase.table("access_requests").insert(payload).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if any(marker in msg for marker in _DUPLICATE_MARKERS):
            # Already requested — idempotent, no enumeration.
            return
        # Table-absent window or transient error: don't 500 the user.
        sentry_sdk.capture_exception(exc)
        logger.error("access_request insert failed (reporting success): %s", exc)
