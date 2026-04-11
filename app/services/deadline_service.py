from typing import Optional

from fastapi import HTTPException

from app.db import supabase
from app.services.helpers import (
    parse_deadline_status_filter,
    parse_due_date_value,
    utc_now_iso,
)


def mark_overdue_deadlines_as_missed(user_id: str) -> None:
    now_iso = utc_now_iso()
    (
        supabase.table("deadlines")
        .update(
            {
                "status": "missed",
                "status_changed_at": now_iso,
            }
        )
        .eq("user_id", user_id)
        .eq("status", "pending")
        .lt("due_date", now_iso)
        .execute()
    )


async def list_deadlines(status: Optional[str], user_id: str) -> dict:
    mark_overdue_deadlines_as_missed(user_id)
    status_filters = parse_deadline_status_filter(status)
    result = (
        supabase.table("deadlines")
        .select("id, description, due_date, status, status_changed_at")
        .eq("user_id", user_id)
        .in_("status", status_filters)
        .order("due_date", desc=False)
        .execute()
    )

    return {"deadlines": result.data}


async def update_deadline_status(deadline_id: str, status: str, user_id: str) -> dict:
    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id, description, due_date, status, status_changed_at")
        .eq("id", deadline_id)
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

    supabase.table("deadlines").delete().eq("id", deadline_id).execute()
    return {"success": True, "id": deadline_id}
