# app/nodes/dedup.py
from app.state import JournalState
from app.embeddings import get_embedding
from app.nodes.store import supabase

async def dedup(state: JournalState) -> dict:
    text = state.get("cleaned_text", state["raw_text"])
    
    # Generate embedding for the cleaned text
    embedding = await get_embedding(text)
    
    # Search for similar existing entries
    result = supabase.rpc("match_entries", {
        "query_embedding": embedding,
        "match_count": 1,
        "filter_user_id": state.get("user_id")
    }).execute()
    
    if result.data and len(result.data) > 0:
        match = result.data[0]
        similarity = match["similarity"]
        print(f"🔍 DEDUP: Closest match '{match['auto_title']}' (sim: {similarity:.3f})")
        
        if similarity > 0.85:
            print(f"⚠️ DUPLICATE DETECTED — skipping pipeline")
            return {
                "dedup_check_result": "duplicate",
                "duplicate_of": match["id"]
            }
    
    print("✅ DEDUP: No duplicate found — continuing pipeline")
    return {"dedup_check_result": "not_duplicate"}