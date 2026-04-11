from typing import Optional

from fastapi import HTTPException

from app.db import supabase
from app.services.deadline_service import mark_overdue_deadlines_as_missed
from app.services.helpers import parse_project_status_filter, utc_now_iso


def get_suppressed_project_entity_ids(user_id: str) -> set[str]:
    result = (
        supabase.table("suppressed_project_entities")
        .select("entity_id")
        .eq("user_id", user_id)
        .execute()
    )

    return {
        row["entity_id"]
        for row in (result.data or [])
        if row.get("entity_id")
    }


def clear_deadline_project_links(project_id: str) -> None:
    try:
        (
            supabase.table("deadlines")
            .update({"project_id": None})
            .eq("project_id", project_id)
            .execute()
        )
    except Exception as exc:
        message = str(exc).lower()
        if "project_id" in message and (
            "column" in message or "schema cache" in message
        ):
            return
        raise


async def list_projects(status: Optional[str], user_id: str) -> dict:
    status_filters = parse_project_status_filter(status)
    result = (
        supabase.table("projects")
        .select(
            "id, name, status, first_mentioned_at, last_mentioned_at, "
            "mention_count, running_summary, status_changed_at"
        )
        .eq("user_id", user_id)
        .in_("status", status_filters)
        .order("mention_count", desc=True)
        .execute()
    )

    return {"projects": result.data}


async def update_project_status(project_id: str, status: str, user_id: str) -> dict:
    project_result = (
        supabase.table("projects")
        .select(
            "id, user_id, name, status, first_mentioned_at, "
            "last_mentioned_at, mention_count, running_summary, "
            "status_changed_at, source_entity_id"
        )
        .eq("id", project_id)
        .limit(1)
        .execute()
    )

    if not project_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_result.data[0]
    if project.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated_result = (
        supabase.table("projects")
        .update(
            {
                "status": status,
                "status_changed_at": utc_now_iso(),
            },
            returning="representation",
        )
        .eq("id", project_id)
        .execute()
    )

    if not updated_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    return updated_result.data[0]


async def delete_project(project_id: str, user_id: str) -> dict:
    project_result = (
        supabase.table("projects")
        .select("id, user_id, source_entity_id")
        .eq("id", project_id)
        .limit(1)
        .execute()
    )

    if not project_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_result.data[0]
    if project.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    source_entity_id = project.get("source_entity_id")
    if source_entity_id:
        (
            supabase.table("suppressed_project_entities")
            .upsert(
                {"user_id": user_id, "entity_id": source_entity_id},
                on_conflict="user_id,entity_id",
            )
            .execute()
        )

    clear_deadline_project_links(project_id)
    supabase.table("projects").delete().eq("id", project_id).execute()
    return {"success": True, "id": project_id}


async def get_progress(user_id: str) -> dict:
    mark_overdue_deadlines_as_missed(user_id)

    deadline_result = (
        supabase.table("deadlines")
        .select("id, description, due_date, status, status_changed_at")
        .eq("user_id", user_id)
        .in_("status", ["done", "missed"])
        .order("status_changed_at", desc=True)
        .execute()
    )

    project_result = (
        supabase.table("projects")
        .select(
            "id, name, mention_count, first_mentioned_at, status, "
            "status_changed_at"
        )
        .eq("user_id", user_id)
        .eq("status", "completed")
        .order("status_changed_at", desc=True)
        .execute()
    )

    return {
        "deadlines": deadline_result.data or [],
        "projects": project_result.data or [],
    }
