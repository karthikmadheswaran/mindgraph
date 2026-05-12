from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.db import supabase
from app.services.deadline_service import mark_overdue_deadlines_as_missed
from app.services.helpers import parse_project_status_filter, utc_now_iso


def _count_recent_mentions_by_entity(user_id: str, entity_ids: list[str], days: int = 7) -> dict[str, int]:
    """Count entry_entities joins to each entity within the trailing window.

    Filters out soft-deleted and non-completed entries — those represent
    pipeline-in-flight or removed entries and shouldn't pad the mention count.
    """
    if not entity_ids:
        return {}

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    recent_entries_resp = (
        supabase.table("entries")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .gte("created_at", since)
        .execute()
    )
    recent_entry_ids = [row["id"] for row in (recent_entries_resp.data or [])]
    if not recent_entry_ids:
        return {entity_id: 0 for entity_id in entity_ids}

    links_resp = (
        supabase.table("entry_entities")
        .select("entity_id, entry_id")
        .in_("entity_id", entity_ids)
        .in_("entry_id", recent_entry_ids)
        .execute()
    )

    counts: dict[str, int] = {entity_id: 0 for entity_id in entity_ids}
    for row in (links_resp.data or []):
        entity_id = row.get("entity_id")
        if entity_id in counts:
            counts[entity_id] += 1
    return counts


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
            "mention_count, running_summary, status_changed_at, source_entity_id"
        )
        .eq("user_id", user_id)
        .in_("status", status_filters)
        .order("mention_count", desc=True)
        .execute()
    )

    projects = result.data or []
    source_entity_ids = [p["source_entity_id"] for p in projects if p.get("source_entity_id")]
    recent_counts = _count_recent_mentions_by_entity(user_id, source_entity_ids, days=7)
    for project in projects:
        source_id = project.get("source_entity_id")
        project["mention_count_last_7d"] = recent_counts.get(source_id, 0) if source_id else 0

    return {"projects": projects}


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
