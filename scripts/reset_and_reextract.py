"""
Full entity reset + re-extraction for all users.

What this does (non-destructive to journal entries):
  1. Delete entity_relations for the user
  2. Delete entry_entities links for the user's entries
  3. Delete entities for the user
  4. Re-run entity extraction on every completed entry (new prompt + 3-stage matching)
  5. Re-run relation backfill for every completed entry

Run with:
    python reset_and_reextract.py
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from app.nodes.extract_entities import extract_entities
from app.nodes.store import resolve_entities, store_entry_entities, supabase
from app.nodes.extract_relations import run_relation_extraction
from app.nodes.store import make_entity_lookup_key, store_relations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_all_users_with_entries() -> list[dict]:
    """Return all users who have at least one completed entry."""
    users_resp = supabase.table("users").select("id, email").execute()
    result = []
    for user in (users_resp.data or []):
        entries_resp = (
            supabase.table("entries")
            .select("id, status, cleaned_text, raw_text, summary")
            .eq("user_id", user["id"])
            .eq("status", "completed")
            .execute()
        )
        entries = entries_resp.data or []
        if entries:
            result.append({"id": user["id"], "email": user["email"], "entries": entries})
    return result


def wipe_entities_for_user(user_id: str) -> None:
    """Delete all entity data for a user. Entries themselves are untouched."""
    # Fetch all entity IDs owned by this user first
    entity_ids_resp = (
        supabase.table("entities").select("id").eq("user_id", user_id).execute()
    )
    entity_ids = [r["id"] for r in (entity_ids_resp.data or [])]

    # Delete entry_entities by entity ownership — catches cross-linked rows too
    if entity_ids:
        supabase.table("entry_entities").delete().in_("entity_id", entity_ids).execute()
        print(f"  Deleted entry_entities links ({len(entity_ids)} entities)")

    supabase.table("entity_relations").delete().eq("user_id", user_id).execute()
    print(f"  Deleted entity_relations")

    supabase.table("entities").delete().eq("user_id", user_id).execute()
    print(f"  Deleted entities")


async def reextract_entities_for_entry(entry: dict, user_id: str) -> dict:
    """Run entity extraction + store for a single entry. Returns entity lookup."""
    text = entry.get("cleaned_text") or entry.get("raw_text") or ""
    summary = entry.get("summary") or ""
    entry_id = entry["id"]

    if not text:
        print(f"    [{entry_id[:8]}] SKIP: no text")
        return {}

    state = {
        "raw_text": text,
        "cleaned_text": text,
        "user_id": user_id,
        "summary": summary,
        "auto_title": "",
        "input_type": "text",
        "attachment_url": "",
        "classifier": [],
        "core_entities": [],
        "deadline": [],
        "relations": [],
        "trigger_check": False,
        "duplicate_of": None,
        "dedup_check_result": None,
        "entry_id": entry_id,
    }

    result = await extract_entities(state)
    entities = result.get("core_entities", [])

    if not entities:
        print(f"    [{entry_id[:8]}] no entities extracted")
        return {}

    entity_result = await resolve_entities(entities, user_id, summary)
    entity_ids = entity_result["ids"]

    if entity_ids:
        unique_ids = list(set(entity_ids))
        await store_entry_entities(entry_id, unique_ids)

    print(
        f"    [{entry_id[:8]}] extracted {len(entities)} entities "
        f"-> stored/linked {len(set(entity_ids))} unique"
    )
    return entity_result["lookup"]


async def reextract_relations_for_entry(entry: dict, user_id: str, entity_lookup: dict) -> None:
    """Re-run relation extraction for a single entry using the rebuilt entity lookup."""
    text = entry.get("cleaned_text") or entry.get("raw_text") or ""
    entry_id = entry["id"]

    if not text or not entity_lookup:
        return

    # Fetch the entities now stored for this entry
    link_resp = (
        supabase.table("entry_entities")
        .select("entity_id")
        .eq("entry_id", entry_id)
        .execute()
    )
    entity_ids = [r["entity_id"] for r in (link_resp.data or []) if r.get("entity_id")]

    if len(entity_ids) < 2:
        return

    entity_rows_resp = (
        supabase.table("entities")
        .select("id, name, entity_type")
        .eq("user_id", user_id)
        .in_("id", entity_ids)
        .execute()
    )
    entity_rows = entity_rows_resp.data or []

    if len(entity_rows) < 2:
        return

    extracted_entities = [{"name": r["name"], "type": r["entity_type"]} for r in entity_rows]
    lookup = {make_entity_lookup_key(r["name"], r["entity_type"]): r["id"] for r in entity_rows}

    try:
        relations = await run_relation_extraction(text, extracted_entities)
        if not relations:
            return
        result = await store_relations(relations, user_id, entry_id, lookup)
        print(
            f"    [{entry_id[:8]}] relations: extracted {len(relations)} "
            f"-> stored {result['stored']} skipped {result['skipped']}"
        )
    except Exception as exc:
        print(f"    [{entry_id[:8]}] relation error: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    users = get_all_users_with_entries()
    total_entries = sum(len(u["entries"]) for u in users)

    print("=" * 70)
    print(f"RESET + RE-EXTRACT: {len(users)} users, {total_entries} entries total")
    print("=" * 70)
    for u in users:
        print(f"  {u['email']:40s} {len(u['entries'])} entries")
    print()

    for user in users:
        user_id = user["id"]
        email = user["email"]
        entries = user["entries"]
        entry_ids = [e["id"] for e in entries]

        print(f"\n{'='*70}")
        print(f"USER: {email} ({user_id[:8]}...)")
        print(f"  Entries to process: {len(entries)}")

        # Step 1: Wipe
        print("\n  [1/3] Wiping existing entity data...")
        wipe_entities_for_user(user_id)

        # Step 2: Re-extract entities
        print(f"\n  [2/3] Re-extracting entities for {len(entries)} entries...")
        entry_lookups: dict[str, dict] = {}
        for entry in entries:
            lookup = await reextract_entities_for_entry(entry, user_id)
            entry_lookups[entry["id"]] = lookup
            await asyncio.sleep(0.3)  # gentle rate limiting

        # Step 3: Re-extract relations
        print(f"\n  [3/3] Re-extracting relations...")
        for entry in entries:
            lookup = entry_lookups.get(entry["id"], {})
            await reextract_relations_for_entry(entry, user_id, lookup)
            await asyncio.sleep(0.3)

        # Summary for this user
        entity_count = (
            supabase.table("entities")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
            .count
        )
        relation_count = (
            supabase.table("entity_relations")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
            .count
        )
        print(f"\n  Done: {entity_count} entities, {relation_count} relations stored")

    print(f"\n{'='*70}")
    print("ALL USERS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
