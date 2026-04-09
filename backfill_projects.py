"""
One-time backfill for projects from existing project entities.

Run after applying migrations/004_status_changed_at.sql:
    python backfill_projects.py
"""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from app.nodes.store import supabase


def backfill_projects() -> None:
    entity_result = (
        supabase.table("entities")
        .select(
            "id, user_id, name, first_seen_at, last_seen_at, "
            "mention_count, context_summary"
        )
        .eq("entity_type", "project")
        .order("user_id")
        .order("mention_count", desc=True)
        .execute()
    )
    project_entities = entity_result.data or []

    existing_result = (
        supabase.table("projects")
        .select("source_entity_id, status")
        .execute()
    )
    existing_project_rows = {
        row["source_entity_id"]: row
        for row in (existing_result.data or [])
        if row.get("source_entity_id")
    }

    suppressed_result = (
        supabase.table("suppressed_project_entities")
        .select("entity_id")
        .execute()
    )
    suppressed_entity_ids = {
        row["entity_id"]
        for row in (suppressed_result.data or [])
        if row.get("entity_id")
    }

    stats = defaultdict(lambda: {"scanned": 0, "created": 0, "updated": 0})

    print(f"Found {len(project_entities)} project entities to sync")

    for entity in project_entities:
        user_stats = stats[entity["user_id"]]
        user_stats["scanned"] += 1

        source_entity_id = entity["id"]
        if source_entity_id in suppressed_entity_ids:
            continue

        existing_row = existing_project_rows.get(source_entity_id)
        already_exists = existing_row is not None

        base_payload = {
            "user_id": entity["user_id"],
            "name": entity["name"],
            "first_mentioned_at": entity.get("first_seen_at"),
            "last_mentioned_at": entity.get("last_seen_at"),
            "mention_count": entity.get("mention_count") or 1,
            "running_summary": entity.get("context_summary"),
            "source_entity_id": source_entity_id,
        }

        if already_exists:
            supabase.table("projects").update(base_payload).eq(
                "source_entity_id", source_entity_id
            ).execute()
            user_stats["updated"] += 1
        else:
            project_id = str(uuid4())
            supabase.table("projects").insert(
                {
                    "id": project_id,
                    "status": "active",
                    "status_changed_at": datetime.now(timezone.utc).isoformat(),
                    **base_payload,
                }
            ).execute()
            user_stats["created"] += 1
            existing_project_rows[source_entity_id] = {
                "id": project_id,
                **base_payload,
                "status": "active",
            }

    print("\nBackfill summary")
    print("-" * 60)
    for user_id, counts in sorted(stats.items()):
        print(
            f"{user_id}: scanned {counts['scanned']}, "
            f"created {counts['created']}, updated {counts['updated']}"
        )


if __name__ == "__main__":
    backfill_projects()
