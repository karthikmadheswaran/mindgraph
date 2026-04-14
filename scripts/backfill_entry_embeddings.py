# backfill_entry_embeddings.py
import asyncio
from app.embeddings import get_embedding
from app.nodes.store import supabase

async def backfill():
    result = supabase.table("entries") \
        .select("id, auto_title, cleaned_text, raw_text") \
        .is_("embedding", "null") \
        .execute()
    
    entries = result.data
    print(f"Found {len(entries)} entries without embeddings\n")
    
    for entry in entries:
        text = entry.get("cleaned_text") or entry.get("raw_text", "")
        title = entry.get("auto_title", "Untitled")
        
        embedding = await get_embedding(text)
        
        supabase.table("entries").update({
            "embedding": embedding
        }).eq("id", entry["id"]).execute()
        
        print(f"✅ {title}")
    
    print(f"\nDone! Backfilled {len(entries)} entries.")

asyncio.run(backfill())