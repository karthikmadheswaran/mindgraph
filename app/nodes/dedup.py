# app/nodes/dedup.py
import logging

from app.db import supabase
from app.state import JournalState
from app.embeddings import get_embedding

logger = logging.getLogger(__name__)

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
        logger.info("Dedup: closest match '%s' (sim=%.3f)", match["auto_title"], similarity)

        if similarity > 0.85:
            logger.info("Duplicate detected; skipping pipeline")
            entry_id = state.get("entry_id")
            duplicate_of = match["id"]
            # Without this, dedup_router routes to END, store/assemble_dispatch never run,
            # and the row stays at status="processing" forever — frontend hangs.
            if entry_id:
                duplicate_payload = {
                    "subject": "Looks like a near-duplicate",
                    "summary": "",
                    "discoveries": [{
                        "type": "duplicate",
                        "phrase": f"very similar to '{match.get('auto_title') or 'an earlier entry'}'",
                    }],
                    "stamps": [],
                    "pipeline_version": "duplicate",
                    "entry_id": str(entry_id),
                    "duplicate_of": duplicate_of,
                }
                try:
                    supabase.table("entries").update({
                        "dispatch_payload": duplicate_payload,
                        "status": "completed",
                        "pipeline_stage": None,
                    }).eq("id", str(entry_id)).execute()
                except Exception as exc:
                    logger.error(
                        "dedup: failed to persist duplicate dispatch_payload for entry %s: %s",
                        entry_id, exc, exc_info=True,
                    )
                    try:
                        supabase.table("entries").update(
                            {"status": "error", "pipeline_stage": None}
                        ).eq("id", str(entry_id)).execute()
                    except Exception:
                        pass
            return {
                "dedup_check_result": "duplicate",
                "duplicate_of": duplicate_of,
            }

    logger.info("No duplicate found; continuing pipeline")
    return {"dedup_check_result": "not_duplicate"}
