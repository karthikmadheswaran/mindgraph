import logging
from datetime import datetime

from postgrest.exceptions import APIError

from app.db import supabase
from app.embeddings import get_embedding
from app.entity_resolver import (
    base_normalize,
    get_match_key,
    make_entity_lookup_key,
    normalize_text,
    project_match_key,
    resolve_entities,
    should_accept_semantic_match,
    store_entities,
)
from app.state import JournalState, RelationEdge

logger = logging.getLogger(__name__)

__all__ = [
    "supabase",
    "base_normalize",
    "project_match_key",
    "get_match_key",
    "should_accept_semantic_match",
    "normalize_text",
    "make_entity_lookup_key",
    "resolve_entities",
    "store_entities",
    "normalize_deadline_description",
    "make_deadline_due_date_key",
    "dedup_deadline_rows",
    "is_duplicate_constraint_error",
    "store_entry",
    "store_entry_tags",
    "store_entry_deadlines",
    "store_entry_entities",
    "store_relations",
    "store_node",
]


def normalize_deadline_description(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def make_deadline_due_date_key(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()

    text = str(value or "").strip()
    if "T" in text:
        return text.split("T", 1)[0]
    return text


def dedup_deadline_rows(deadlines: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique_deadlines: list[dict] = []

    for deadline in deadlines:
        key = (
            normalize_deadline_description(deadline.get("description", "")),
            make_deadline_due_date_key(deadline.get("due_at")),
        )
        if key in seen:
            continue

        seen.add(key)
        unique_deadlines.append(deadline)

    return unique_deadlines


def is_duplicate_constraint_error(exc: Exception) -> bool:
    if isinstance(exc, APIError):
        code = getattr(exc, "code", None)
        if code == "23505":
            return True

    message = str(exc).lower()
    return "23505" in message or "duplicate key value violates unique constraint" in message


async def store_entry(state: JournalState) -> dict:
    embedding = await get_embedding(state.get("cleaned_text", state["raw_text"]))
    data = {
        "raw_text": state["raw_text"],
        "cleaned_text": state.get("cleaned_text", ""),
        "auto_title": state.get("auto_title", ""),
        "summary": state.get("summary", ""),
        "user_id": state.get("user_id", ""),
        "embedding": embedding,
    }

    entry_id = state.get("entry_id")
    if entry_id:
        data["status"] = "completed"
        data["pipeline_stage"] = None
        supabase.table("entries").update(data).eq("id", entry_id).execute()
        return {"id": entry_id}

    result = supabase.table("entries").insert(data).execute()
    return {"id": result.data[0]["id"]} if result.data else {"error": "Failed to store entry"}


async def store_entry_tags(entry_id: int, tags: list[str]) -> dict:
    if not tags:
        return {"success": True}

    tag_data = [{"entry_id": entry_id, "confidence": 1.0, "category": tag} for tag in tags]
    result = supabase.table("entry_tags").insert(tag_data).execute()
    return {"success": True} if result.data else {"error": "Failed to store tags"}


async def store_entry_deadlines(entry_id: int, deadlines: list[dict], user_id: str) -> dict:
    if not deadlines:
        return {"success": True}

    unique_deadlines = dedup_deadline_rows(deadlines)

    deadline_data = [
        {
            "source_entry_id": entry_id,
            "user_id": user_id,
            "description": deadline["description"],
            "due_date": deadline["due_at"].isoformat(),
        }
        for deadline in unique_deadlines
    ]

    stored = 0
    skipped_duplicates = len(deadlines) - len(unique_deadlines)

    for row in deadline_data:
        try:
            result = supabase.table("deadlines").insert(row).execute()
            if result.data:
                stored += 1
        except Exception as exc:
            if is_duplicate_constraint_error(exc):
                skipped_duplicates += 1
                continue
            return {"error": f"Failed to store deadlines: {exc}"}

    return {
        "success": True,
        "stored": stored,
        "skipped_duplicates": skipped_duplicates,
    }


async def store_entry_entities(entry_id: str, entity_ids: list[str]) -> dict:
    if not entity_ids:
        return {"success": True}

    data = [{"entry_id": entry_id, "entity_id": entity_id} for entity_id in entity_ids]
    result = supabase.table("entry_entities").insert(data).execute()
    return {"success": True} if result.data else {"error": "Failed to link entities"}


async def store_relations(
    relations: list[RelationEdge],
    user_id: str,
    entry_id: str,
    entity_lookup: dict[str, str],
) -> dict:
    if not relations:
        return {"success": True, "stored": 0, "skipped": 0}

    stored = 0
    skipped = 0

    for relation in relations:
        source_key = make_entity_lookup_key(
            relation["source"],
            relation["source_type"],
        )
        target_key = make_entity_lookup_key(
            relation["target"],
            relation["target_type"],
        )

        source_id = entity_lookup.get(source_key)
        target_id = entity_lookup.get(target_key)

        if not source_id or not target_id or source_id == target_id:
            skipped += 1
            continue

        if relation["relation"] == "works_with" and source_id > target_id:
            source_id, target_id = target_id, source_id

        try:
            supabase.table("entity_relations").upsert(
                {
                    "user_id": user_id,
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "relation_type": relation["relation"],
                    "confidence": 1.0,
                    "source_entry_id": entry_id,
                    "updated_at": datetime.now().isoformat(),
                },
                on_conflict="user_id,source_entity_id,target_entity_id,relation_type",
            ).execute()
            stored += 1
        except Exception as exc:
            logger.warning(
                "Relation store failed for relation=%s: %s",
                relation,
                exc,
                exc_info=True,
            )
            skipped += 1

    return {"success": True, "stored": stored, "skipped": skipped}


async def store_node(state: JournalState) -> dict:
    if state.get("dedup_check_result") == "duplicate":
        logger.info("Duplicate of entry %s; skipping store", state.get("duplicate_of"))
        return {}

    try:
        entry_result = await store_entry(state)
        logger.info("Entry stored: %s", entry_result)

        if "error" in entry_result:
            return {}

        entry_id = entry_result["id"]

        tags_result = await store_entry_tags(entry_id, state.get("classifier", []))
        logger.info("Tags stored: %s", tags_result)

        entity_result = await resolve_entities(
            state.get("core_entities", []),
            state.get("user_id", ""),
            state.get("summary", ""),
        )
        entity_ids = entity_result["ids"]
        logger.info("Entities resolved: %s", entity_ids)

        unique_entity_ids = list(set(entity_ids))
        entity_link_result = await store_entry_entities(entry_id, unique_entity_ids)
        logger.info("Entity links stored: %s", entity_link_result)

        relations_result = await store_relations(
            state.get("relations", []),
            state.get("user_id", ""),
            entry_id,
            entity_result["lookup"],
        )
        logger.info("Relations stored: %s", relations_result)

        deadlines_result = await store_entry_deadlines(
            entry_id,
            state.get("deadline", []),
            state.get("user_id", ""),
        )
        logger.info("Deadlines stored: %s", deadlines_result)

    except Exception as exc:
        logger.error("Store node failed: %s", exc, exc_info=True)

    return {}
