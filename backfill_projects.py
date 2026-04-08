"""
One-time backfill for projects from existing project entities.

Run after applying migrations/002_sync_projects_from_entities.sql:
    python backfill_projects.py
"""

from collections import defaultdict
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
        .select("source_entity_id")
        .execute()
    )
    existing_source_ids = {
        row["source_entity_id"]
        for row in (existing_result.data or [])
        if row.get("source_entity_id")
    }

    stats = defaultdict(lambda: {"scanned": 0, "created": 0, "updated": 0})

    print(f"Found {len(project_entities)} project entities to sync")

    for entity in project_entities:
        user_stats = stats[entity["user_id"]]
        user_stats["scanned"] += 1

        source_entity_id = entity["id"]
        already_exists = source_entity_id in existing_source_ids

        supabase.table("projects").upsert(
            {
                "id": str(uuid4()),
                "user_id": entity["user_id"],
                "name": entity["name"],
                "status": "active",
                "first_mentioned_at": entity.get("first_seen_at"),
                "last_mentioned_at": entity.get("last_seen_at"),
                "mention_count": entity.get("mention_count") or 1,
                "running_summary": entity.get("context_summary"),
                "source_entity_id": source_entity_id,
            },
            on_conflict="source_entity_id",
        ).execute()

        if already_exists:
            user_stats["updated"] += 1
        else:
            user_stats["created"] += 1
            existing_source_ids.add(source_entity_id)

    print("\nBackfill summary")
    print("-" * 60)
    for user_id, counts in sorted(stats.items()):
        print(
            f"{user_id}: scanned {counts['scanned']}, "
            f"created {counts['created']}, updated {counts['updated']}"
        )


if __name__ == "__main__":
    backfill_projects()
