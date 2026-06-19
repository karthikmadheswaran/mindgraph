from typing import Optional

from fastapi import HTTPException

from app.db import supabase
from app.services.helpers import (
    parse_deadline_status_filter,
    parse_due_date_value,
    utc_now_iso,
)


def mark_overdue_deadlines_as_missed(user_id: str) -> None:
    """Idempotently reconcile deadline status against current time.

    pending + past  -> missed   (overdue items slip naturally)
    missed  + future -> pending (snoozing a missed deadline graduates it back)
    """
    now_iso = utc_now_iso()
    (
        supabase.table("deadlines")
        .update({"status": "missed", "status_changed_at": now_iso})
        .eq("user_id", user_id)
        .eq("status", "pending")
        .lt("due_date", now_iso)
        .is_("deleted_at", "null")
        .execute()
    )
    (
        supabase.table("deadlines")
        .update({"status": "pending", "status_changed_at": now_iso})
        .eq("user_id", user_id)
        .eq("status", "missed")
        .gte("due_date", now_iso)
        .is_("deleted_at", "null")
        .execute()
    )


async def list_deadlines(status: Optional[str], user_id: str) -> dict:
    mark_overdue_deadlines_as_missed(user_id)
    status_filters = parse_deadline_status_filter(status)

    # Only surface deadlines whose parent entry is completed and not soft-deleted.
    # Pipeline-stuck or deleted-entry deadlines should not appear on the dashboard.
    visible_entries = (
        supabase.table("entries")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .execute()
    )
    visible_entry_ids = [row["id"] for row in (visible_entries.data or [])]
    if not visible_entry_ids:
        return {"deadlines": []}

    sort_descending = "missed" in status_filters and "pending" not in status_filters
    result = (
        supabase.table("deadlines")
        .select("id, description, due_date, status, status_changed_at, source_entry_id")
        .eq("user_id", user_id)
        .in_("status", status_filters)
        .in_("source_entry_id", visible_entry_ids)
        .is_("deleted_at", "null")
        .order("due_date", desc=sort_descending)
        .execute()
    )

    return {"deadlines": result.data}


async def update_deadline_status(deadline_id: str, status: str, user_id: str) -> dict:
    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id, description, due_date, status, status_changed_at")
        .eq("id", deadline_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    if not deadline_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    deadline = deadline_result.data[0]
    if deadline.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated_result = (
        supabase.table("deadlines")
        .update(
            {
                "status": status,
                "status_changed_at": utc_now_iso(),
            },
            returning="representation",
        )
        .eq("id", deadline_id)
        .execute()
    )

    if not updated_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    return updated_result.data[0]


async def update_deadline_date(deadline_id: str, due_date: str, user_id: str) -> dict:
    parsed_due_date = parse_due_date_value(due_date)

    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id, description, due_date, status, status_changed_at")
        .eq("id", deadline_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    if not deadline_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    deadline = deadline_result.data[0]
    if deadline.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated_result = (
        supabase.table("deadlines")
        .update({"due_date": parsed_due_date.isoformat()}, returning="representation")
        .eq("id", deadline_id)
        .execute()
    )

    if not updated_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    return updated_result.data[0]


async def delete_deadline(deadline_id: str, user_id: str) -> dict:
    # Soft delete: stamp deleted_at instead of removing the row, so the deadline
    # stays recoverable (5s client undo + the restore endpoint below). Every read
    # path filters `deleted_at IS NULL`. The guard SELECT also filters it so a
    # second delete of an already-deleted row is a clean 404, not a no-op.
    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id")
        .eq("id", deadline_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    if not deadline_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    deadline = deadline_result.data[0]
    if deadline.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    supabase.table("deadlines").update(
        {"deleted_at": utc_now_iso()}
    ).eq("id", deadline_id).execute()
    return {"success": True, "id": deadline_id}


async def restore_deadline(deadline_id: str, user_id: str) -> dict:
    # Recovery beyond the 5s undo window: clear deleted_at. The ownership SELECT
    # here deliberately does NOT filter deleted_at — we are looking up a
    # soft-deleted row precisely to bring it back.
    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id")
        .eq("id", deadline_id)
        .limit(1)
        .execute()
    )

    if not deadline_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    deadline = deadline_result.data[0]
    if deadline.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        updated_result = (
            supabase.table("deadlines")
            .update({"deleted_at": None}, returning="representation")
            .eq("id", deadline_id)
            .execute()
        )
    except Exception as exc:
        # The partial unique index (migration 017) only constrains live rows, so
        # restoring into an existing live duplicate (same source_entry_id,
        # lower(description), due_date) raises a unique violation. Surface 409,
        # not a 500.
        message = str(exc).lower()
        if (
            "23505" in message
            or "duplicate key" in message
            or "idx_deadlines_source_entry_description_due_date" in message
        ):
            raise HTTPException(
                status_code=409,
                detail="A matching deadline already exists; cannot restore the duplicate.",
            )
        raise

    if not updated_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    return updated_result.data[0]
