# backfill_embeddings.py
import asyncio
from app.embeddings import get_embedding
from app.nodes.store import supabase

async def backfill():
    # Step 1: Get all entities without embeddings
    result = supabase.table("entities") \
        .select("id, name, entity_type, context_summary") \
        .is_("embedding", "null") \
        .execute()
    
    entities = result.data
    print(f"Found {len(entities)} entities without embeddings\n")
    
    for entity in entities:
        # Step 2: Build description text
        name = entity["name"]
        etype = entity["entity_type"] or "unknown"
        context = entity["context_summary"] or ""
        description = f"{name} ({etype}): {context}"
        
        # Step 3: Generate embedding
        embedding = await get_embedding(description)
        
        # Step 4: Update the row
        supabase.table("entities").update({
            "embedding": embedding
        }).eq("id", entity["id"]).execute()
        
        print(f"✅ {name} ({etype})")
    
    print(f"\nDone! Backfilled {len(entities)} entities.")

asyncio.run(backfill())