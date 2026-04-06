import os
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client

from app.embeddings import get_embedding
from app.state import JournalState, RelationEdge

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
)


def should_accept_semantic_match(incoming_name: str, matched_name: str, similarity: float) -> bool:
    incoming = incoming_name.strip().lower()
    matched = matched_name.strip().lower()

    if similarity >= 0.95:
        return True

    if incoming in matched or matched in incoming:
        return similarity >= 0.90

    return False


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def make_entity_lookup_key(name: str, entity_type: str) -> str:
    return f"{normalize_text(name)}|{normalize_text(entity_type)}"


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


async def resolve_entities(entities: list[dict], user_id: str, summary: str) -> dict:
    if not entities:
        return {"ids": [], "lookup": {}}

    entity_ids: list[str] = []
    entity_lookup: dict[str, str] = {}

    for entity in entities:
        entity_name = entity["name"].strip()
        entity_type = entity["type"]
        normalized_name = entity_name.lower()
        input_lookup_key = make_entity_lookup_key(entity_name, entity_type)

        exact_match = (
            supabase.table("entities")
            .select("id, name, entity_type, mention_count")
            .eq("user_id", user_id)
            .eq("entity_type", entity_type)
            .ilike("name", entity_name)
            .limit(1)
            .execute()
        )

        if exact_match.data and len(exact_match.data) > 0:
            matched = exact_match.data[0]

            print(
                f"EXACT CASE-INSENSITIVE MATCH: incoming='{entity_name}' "
                f"normalized='{normalized_name}' matched='{matched['name']}'"
            )

            supabase.table("entities").update({
                "mention_count": matched["mention_count"] + 1,
                "last_seen_at": datetime.now().isoformat(),
                "context_summary": summary,
            }).eq("id", matched["id"]).execute()

            entity_ids.append(matched["id"])
            entity_lookup[input_lookup_key] = matched["id"]
            entity_lookup[make_entity_lookup_key(matched["name"], matched["entity_type"])] = matched["id"]
            continue

        description = f"{entity_name} ({entity_type}) - {summary}"
        embedding = await get_embedding(description)

        match_result = supabase.rpc("match_entities", {
            "query_embedding": embedding,
            "match_count": 3,
            "filter_user_id": user_id,
            "similarity_threshold": 0.8,
            "filter_entity_type": entity_type
        }).execute()

        if match_result.data and len(match_result.data) > 0:
            print(f"Candidates for '{entity_name}':")
            for match in match_result.data:
                print(
                    f"  - '{match['name']}' "
                    f"(type: {match['entity_type']}, sim: {match['similarity']:.3f})"
                )

            matched = match_result.data[0]
            similarity = matched["similarity"]

            if should_accept_semantic_match(entity_name, matched["name"], similarity):
                print(
                    f"SEMANTIC MATCH ACCEPTED: '{entity_name}' -> '{matched['name']}' "
                    f"(type: {matched['entity_type']}, sim: {similarity:.3f})"
                )

                supabase.table("entities").update({
                    "mention_count": matched["mention_count"] + 1,
                    "last_seen_at": datetime.now().isoformat(),
                    "context_summary": summary
                }).eq("id", matched["id"]).execute()

                entity_ids.append(matched["id"])
                entity_lookup[input_lookup_key] = matched["id"]
                entity_lookup[make_entity_lookup_key(matched["name"], matched["entity_type"])] = matched["id"]
            else:
                print(
                    f"SEMANTIC MATCH REJECTED: '{entity_name}' -> '{matched['name']}' "
                    f"(type: {matched['entity_type']}, sim: {similarity:.3f})"
                )
                print(f"NEW ENTITY: {entity_name} ({entity_type})")

                new_entity = supabase.table("entities").insert({
                    "user_id": user_id,
                    "name": entity_name,
                    "entity_type": entity_type,
                    "first_seen_at": datetime.now().isoformat(),
                    "last_seen_at": datetime.now().isoformat(),
                    "mention_count": 1,
                    "embedding": embedding,
                    "context_summary": summary
                }).execute()

                if new_entity.data:
                    entity_ids.append(new_entity.data[0]["id"])
                    entity_lookup[input_lookup_key] = new_entity.data[0]["id"]
        else:
            print(f"NEW ENTITY: {entity_name} ({entity_type})")

            new_entity = supabase.table("entities").insert({
                "user_id": user_id,
                "name": entity_name,
                "entity_type": entity_type,
                "first_seen_at": datetime.now().isoformat(),
                "last_seen_at": datetime.now().isoformat(),
                "mention_count": 1,
                "embedding": embedding,
                "context_summary": summary
            }).execute()

            if new_entity.data:
                entity_ids.append(new_entity.data[0]["id"])
                entity_lookup[input_lookup_key] = new_entity.data[0]["id"]

    return {"ids": entity_ids, "lookup": entity_lookup}


async def store_entities(entities: list[dict], user_id: str, summary: str) -> list[str]:
    result = await resolve_entities(entities, user_id, summary)
    return result["ids"]


async def store_entry_deadlines(entry_id: int, deadlines: list[dict], user_id: str) -> dict:
    if not deadlines:
        return {"success": True}

    deadline_data = [
        {
            "source_entry_id": entry_id,
            "user_id": user_id,
            "description": deadline["description"],
            "due_date": deadline["due_at"].isoformat(),
        }
        for deadline in deadlines
    ]
    result = supabase.table("deadlines").insert(deadline_data).execute()
    return {"success": True} if result.data else {"error": "Failed to store deadlines"}


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
            print(f"RELATION STORE WARNING: failed to store {relation}: {exc}")
            skipped += 1

    return {"success": True, "stored": stored, "skipped": skipped}


async def store_node(state: JournalState) -> dict:
    if state.get("dedup_check_result") == "duplicate":
        print(f"DUPLICATE of entry {state.get('duplicate_of')} - skipping store")
        return {}

    try:
        entry_result = await store_entry(state)
        print("ENTRY:", entry_result)

        if "error" in entry_result:
            return {}

        entry_id = entry_result["id"]

        tags_result = await store_entry_tags(entry_id, state.get("classifier", []))
        print("TAGS:", tags_result)

        entity_result = await resolve_entities(
            state.get("core_entities", []),
            state.get("user_id", ""),
            state.get("summary", "")
        )
        entity_ids = entity_result["ids"]
        print("ENTITIES:", entity_ids)

        unique_entity_ids = list(set(entity_ids))
        entity_link_result = await store_entry_entities(entry_id, unique_entity_ids)
        print("LINKS:", entity_link_result)

        relations_result = await store_relations(
            state.get("relations", []),
            state.get("user_id", ""),
            entry_id,
            entity_result["lookup"],
        )
        print("RELATIONS:", relations_result)

        deadlines_result = await store_entry_deadlines(
            entry_id,
            state.get("deadline", []),
            state.get("user_id", "")
        )
        print("DEADLINES:", deadlines_result)

    except Exception as exc:
        print(f"STORE ERROR: {exc}")

    return {}
