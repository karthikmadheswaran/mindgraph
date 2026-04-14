"""
One-time backfill for entity relations.

Run with:
    python backfill_relations.py
"""

import asyncio

from app.nodes.extract_relations import run_relation_extraction
from app.nodes.store import make_entity_lookup_key, store_relations, supabase


async def backfill() -> None:
    entries_result = (
        supabase.table("entries")
        .select("id, user_id, cleaned_text, raw_text, status")
        .eq("status", "completed")
        .order("created_at", desc=True)
        .execute()
    )

    entries = entries_result.data or []
    print(f"Found {len(entries)} completed entries")

    for entry in entries:
        entry_id = entry["id"]
        user_id = entry["user_id"]
        text = entry.get("cleaned_text") or entry.get("raw_text") or ""

        if not text:
            print(f"Skipping {entry_id[:8]}: no text")
            continue

        link_result = (
            supabase.table("entry_entities")
            .select("entity_id")
            .eq("entry_id", entry_id)
            .execute()
        )

        entity_ids = [
            row["entity_id"]
            for row in (link_result.data or [])
            if row.get("entity_id")
        ]

        if len(entity_ids) < 2:
            print(f"Skipping {entry_id[:8]}: fewer than 2 linked entities")
            continue

        entity_result = (
            supabase.table("entities")
            .select("id, name, entity_type")
            .eq("user_id", user_id)
            .in_("id", entity_ids)
            .execute()
        )

        entity_rows = entity_result.data or []
        if len(entity_rows) < 2:
            print(f"Skipping {entry_id[:8]}: linked entity rows not found")
            continue

        extracted_entities = [
            {"name": row["name"], "type": row["entity_type"]}
            for row in entity_rows
        ]
        entity_lookup = {
            make_entity_lookup_key(row["name"], row["entity_type"]): row["id"]
            for row in entity_rows
        }

        try:
            relations = await run_relation_extraction(text, extracted_entities)
            if not relations:
                print(f"Entry {entry_id[:8]}: no semantic relations")
                await asyncio.sleep(0.5)
                continue

            result = await store_relations(relations, user_id, entry_id, entity_lookup)
            print(
                f"Entry {entry_id[:8]}: extracted {len(relations)} relations -> "
                f"stored {result['stored']} skipped {result['skipped']}"
            )
        except Exception as exc:
            print(f"Entry {entry_id[:8]}: ERROR {exc}")

        await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(backfill())
