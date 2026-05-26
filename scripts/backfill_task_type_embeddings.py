"""
Backfill embeddings with explicit Gemini task_type.

- entries: RETRIEVAL_DOCUMENT (matches the new live default in app/embeddings.py)
- entities: SEMANTIC_SIMILARITY (entity-to-entity matching is symmetric)

Safety contract:
- Only touches non-deleted, completed entries.
- Generates ALL new embeddings into memory first; writes only after every row succeeds.
- Final write is a single Postgres transaction via bulk_update_*_embeddings RPCs
  (see migrations/015_bulk_update_embeddings_rpcs.sql).
- Prompts y/N before any write.
- Does NOT update entity_resolver.py live code paths — flagged at end of run.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root: `python scripts/backfill_task_type_embeddings.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import supabase
from app.embeddings import get_embedding

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Rough estimate: Gemini embedding-001 is ~$0.000025 per 1k tokens at the time
# of writing. Most journal entries are <500 tokens; entity descriptions <50 tokens.
# We log a back-of-envelope cost so the run leaves a trail.
ENTRY_COST_PER_ROW = 0.0000125
ENTITY_COST_PER_ROW = 0.0000025


def _prompt_yes_no(question: str) -> bool:
    answer = input(f"{question} ").strip().lower()
    return answer in ("y", "yes")


async def _embed_entries() -> list[dict]:
    result = (
        supabase.table("entries")
        .select("id, auto_title, cleaned_text, raw_text")
        .is_("deleted_at", "null")
        .eq("status", "completed")
        .execute()
    )
    rows = result.data or []
    print(f"\n[entries] {len(rows)} rows match (deleted_at IS NULL, status='completed').")
    if not rows:
        return []
    if not _prompt_yes_no("[entries] Proceed to embed? y/N:"):
        print("[entries] Aborted by user.")
        return []

    pairs: list[dict] = []
    for i, row in enumerate(rows, 1):
        text = row.get("cleaned_text") or row.get("raw_text") or ""
        if not text:
            print(f"  [{i}/{len(rows)}] SKIP empty: {row.get('auto_title') or row['id']}")
            continue
        embedding = await get_embedding(text, task_type="RETRIEVAL_DOCUMENT")
        pairs.append({"id": row["id"], "embedding": embedding})
        title = row.get("auto_title") or "(untitled)"
        print(f"  [{i}/{len(rows)}] embedded: {title}")
    return pairs


async def _embed_entities() -> list[dict]:
    result = (
        supabase.table("entities")
        .select("id, name, entity_type, context_summary")
        .execute()
    )
    rows = result.data or []
    print(f"\n[entities] {len(rows)} rows match.")
    if not rows:
        return []
    if not _prompt_yes_no("[entities] Proceed to embed (SEMANTIC_SIMILARITY)? y/N:"):
        print("[entities] Aborted by user.")
        return []

    pairs: list[dict] = []
    for i, row in enumerate(rows, 1):
        name = row.get("name") or ""
        etype = row.get("entity_type") or ""
        summary = row.get("context_summary") or ""
        # Mirror the live resolver's description shape so embeddings stay comparable.
        description = f"{name} ({etype}) - {summary}".strip(" -")
        if not name:
            print(f"  [{i}/{len(rows)}] SKIP nameless: {row['id']}")
            continue
        embedding = await get_embedding(description, task_type="SEMANTIC_SIMILARITY")
        pairs.append({"id": row["id"], "embedding": embedding})
        print(f"  [{i}/{len(rows)}] embedded: {name} ({etype})")
    return pairs


def _bulk_write(rpc_name: str, pairs: list[dict]) -> int:
    if not pairs:
        return 0
    response = supabase.rpc(rpc_name, {"updates": pairs}).execute()
    # Supabase returns the scalar in .data for plpgsql RETURNS int functions.
    return response.data if isinstance(response.data, int) else len(pairs)


async def main() -> None:
    started = time.time()
    started_iso = datetime.now(timezone.utc).isoformat()

    print("=" * 60)
    print("Backfill task_type-aware embeddings")
    print("=" * 60)

    entry_pairs = await _embed_entries()
    entity_pairs = await _embed_entities()

    if not entry_pairs and not entity_pairs:
        print("\nNothing to write. Exiting.")
        return

    print("\nAll embeddings generated. Ready to write.")
    print(f"  entries:  {len(entry_pairs)}")
    print(f"  entities: {len(entity_pairs)}")
    if not _prompt_yes_no("Commit to DB? y/N:"):
        print("Aborted before write. No DB changes made.")
        return

    entry_written = _bulk_write("bulk_update_entry_embeddings", entry_pairs)
    entity_written = _bulk_write("bulk_update_entity_embeddings", entity_pairs)
    finished_iso = datetime.now(timezone.utc).isoformat()
    elapsed = time.time() - started

    est_cost = (
        len(entry_pairs) * ENTRY_COST_PER_ROW
        + len(entity_pairs) * ENTITY_COST_PER_ROW
    )

    print("\n" + "=" * 60)
    print("DONE")
    print(f"  entries written:  {entry_written}")
    print(f"  entities written: {entity_written}")
    print(f"  elapsed:          {elapsed:.1f}s")
    print(f"  est. cost (USD):  ${est_cost:.6f}")
    print("=" * 60)
    print("\nFLAG: entity_resolver.py call sites NOT updated — do this in a follow-up "
          "task after eval.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    record_path = RESULTS_DIR / f"backfill_task_type_{started_iso.replace(':', '-')}.json"
    record = {
        "started_at": started_iso,
        "finished_at": finished_iso,
        "elapsed_seconds": elapsed,
        "entry_task_type": "RETRIEVAL_DOCUMENT",
        "entity_task_type": "SEMANTIC_SIMILARITY",
        "entry_ids": [p["id"] for p in entry_pairs],
        "entity_ids": [p["id"] for p in entity_pairs],
        "entries_written": entry_written,
        "entities_written": entity_written,
        "estimated_cost_usd": est_cost,
        "entity_resolver_updated": False,
    }
    record_path.write_text(json.dumps(record, indent=2))
    print(f"\nRecord written: {record_path}")


if __name__ == "__main__":
    asyncio.run(main())
