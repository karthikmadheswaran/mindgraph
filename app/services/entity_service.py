from app.db import supabase
from app.services.project_service import get_suppressed_project_entity_ids


async def get_entities(user_id: str) -> dict:
    suppressed_entity_ids = get_suppressed_project_entity_ids(user_id)
    result = (
        supabase.table("entities")
        .select("id, name, entity_type, mention_count")
        .eq("user_id", user_id)
        .order("mention_count", desc=True)
        .limit(60)
        .execute()
    )

    entities = [
        entity
        for entity in (result.data or [])
        if not (
            entity.get("entity_type") == "project"
            and entity.get("id") in suppressed_entity_ids
        )
    ][:20]

    return {"entities": entities}


async def get_entity_relations(user_id: str) -> dict:
    suppressed_entity_ids = get_suppressed_project_entity_ids(user_id)
    relation_result = (
        supabase.table("entity_relations")
        .select(
            "source_entity_id, target_entity_id, relation_type, "
            "confidence, source_entry_id, updated_at"
        )
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(200)
        .execute()
    )

    relation_rows = [
        row
        for row in (relation_result.data or [])
        if row.get("source_entity_id") not in suppressed_entity_ids
        and row.get("target_entity_id") not in suppressed_entity_ids
    ]
    entity_ids = sorted(
        {
            row["source_entity_id"]
            for row in relation_rows
            if row.get("source_entity_id")
        }
        | {
            row["target_entity_id"]
            for row in relation_rows
            if row.get("target_entity_id")
        }
    )

    if not entity_ids:
        return {"relations": []}

    entity_result = (
        supabase.table("entities")
        .select("id, name, entity_type")
        .eq("user_id", user_id)
        .in_("id", entity_ids)
        .execute()
    )

    entity_lookup = {
        entity["id"]: entity
        for entity in (entity_result.data or [])
    }

    relations = []
    for row in relation_rows:
        source = entity_lookup.get(row.get("source_entity_id"))
        target = entity_lookup.get(row.get("target_entity_id"))

        if not source or not target:
            continue

        relations.append(
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "source_type": source["entity_type"],
                "target_id": target["id"],
                "target_name": target["name"],
                "target_type": target["entity_type"],
                "relation_type": row["relation_type"],
                "confidence": row.get("confidence", 1.0),
                "source_entry_id": row.get("source_entry_id"),
                "updated_at": row.get("updated_at"),
            }
        )

    return {"relations": relations}
