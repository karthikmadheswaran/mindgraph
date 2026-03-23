# store.py
import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime

from app.state import JournalState
from app.embeddings import get_embedding


load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

async def store_entry(state: JournalState) -> dict:
    #Store the journal entry and its metadata in Supabase
    embedding = await get_embedding(state.get("cleaned_text", state["raw_text"]))
    data = {
        "raw_text": state['raw_text'],
        "cleaned_text": state.get('cleaned_text', ''),
        "auto_title": state.get('auto_title', ''),
        "summary": state.get('summary', ''),
        "user_id": state.get('user_id', ''),
        "embedding": embedding,
    }
    result = supabase.table("entries").insert(data).execute()
    return {"id": result.data[0]["id"]} if result.data else {"error": "Failed to store entry"}

async def store_entry_tags(entry_id: int, tags: list[str]) -> dict:
    #Store the tags for a journal entry in Supabase
    if not tags:
        return {"success": True}
    tag_data = [{"entry_id": entry_id,"confidence": 1.0,"category": tag} for tag in tags]
    result = supabase.table("entry_tags").insert(tag_data).execute()
    return {"success": True} if result.data else {"error": "Failed to store tags"}

async def store_entities(entities: list[dict], user_id: str, summary: str) -> list[str]:
    if not entities:
        return []
    
    
    entity_ids=[]

    for entity in entities:

        description = f"{entity['name']} ({entity['type']}) - {summary}"

        embedding = await get_embedding(description)

        match_result = supabase.rpc("match_entities", {
            "query_embedding": embedding,
            "match_count": 3,
            "filter_user_id": user_id,
            "similarity_threshold": 0.8,
            "filter_entity_type": entity["type"]
        }).execute()

        if match_result.data and len(match_result.data) > 0:
            print(f"🔍 Candidates for '{entity['name']}':")
            for m in match_result.data:
                print(f"   - '{m['name']}' (type: {m['entity_type']}, sim: {m['similarity']:.3f})")
            matched = match_result.data[0]
            print(f"🔍 MATCH: '{entity['name']}' → '{matched['name']}' (type: {matched['entity_type']}, sim: {matched['similarity']:.3f})")

            supabase.table("entities").update({
                "mention_count": matched["mention_count"]+1,
                "last_seen_at": datetime.now().isoformat(),
                "context_summary": summary
            }).eq("id", matched["id"]).execute()

            entity_ids.append(matched["id"])

        else:
            print(f"🆕NEW ENTITY: {entity['name']} ({entity['type']})")

            new_entity=supabase.table("entities").insert({
                "user_id": user_id,
                "name": entity["name"],
                "entity_type": entity["type"],
                "first_seen_at": datetime.now().isoformat(),
                "last_seen_at": datetime.now().isoformat(),
                "embedding": embedding,
                "context_summary": summary
            }).execute()

            if new_entity.data:
                entity_ids.append(new_entity.data[0]["id"])
    
    return entity_ids

async def store_entry_deadlines(entry_id: int, deadlines: list[dict], user_id: str) -> dict:
    # Store the deadlines for a journal entry in Supabase
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
    data = [{"entry_id": entry_id, "entity_id": eid} for eid in entity_ids]
    result = supabase.table("entry_entities").insert(data).execute()
    return {"success": True} if result.data else {"error": "Failed to link entities"}


async def store_node(state: JournalState) -> dict:
    if state.get("dedup_check_result") == "duplicate":
        print(f"⚠️ DUPLICATE of entry {state.get('duplicate_of')} — skipping store")
        return {}
    try:
        entry_result = await store_entry(state)
        print("📦 ENTRY:", entry_result)
        
        if "error" in entry_result:
            return {}
        
        entry_id = entry_result["id"]
        
        tags_result = await store_entry_tags(entry_id, state.get("classifier", []))
        print("🏷️ TAGS:", tags_result)
        
        entity_ids = await store_entities(
            state.get("core_entities", []),
            state.get("user_id", ""),
            state.get("summary", "")
        )    
        print("👤 ENTITIES:", entity_ids)
        # Remove duplicates before linking
        unique_entity_ids = list(set(entity_ids))
        entity_link_result = await store_entry_entities(entry_id, unique_entity_ids)

        print("🔗 LINKS:", entity_link_result)
        
        deadlines_result = await store_entry_deadlines(entry_id, state.get("deadline", []), state.get("user_id", ""))
        print("⏰ DEADLINES:", deadlines_result)
        
    except Exception as e:
        print(f"❌ STORE ERROR: {e}")
    
    return {}