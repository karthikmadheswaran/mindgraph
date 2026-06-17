# app/nodes/dedup.py
import logging

from app.db import supabase
from app.state import JournalState
from app.embeddings import get_embedding

logger = logging.getLogger(__name__)

# Cosine-similarity cutoff for treating a new entry as a near-duplicate of the
# closest existing entry. Crossing it routes the graph to END (dedup_router),
# so the entry is NEVER stored/extracted — a false positive silently swallows a
# real entry (empty cleaned_text/title/entities). Calibrated against real data
# (evals/dedup_threshold_calibration.py): across one user's 59 distinct journal
# entries the MAX distinct-pair cosine was 0.8904 (p99 0.8523) — journal prose in
# a consistent voice clusters tightly — while true accidental re-submits embed
# ~identically (~0.97-1.0). The original 0.85 sat *inside* the distinct-pair band
# (a real, unrelated entry pair scored 0.8596 and was wrongly dropped). 0.92
# clears the observed distinct-pair max with margin while still catching real
# re-submits.
DEDUP_SIMILARITY_THRESHOLD = 0.92


def is_duplicate_similarity(similarity: float) -> bool:
    """True when the nearest existing entry is similar enough to treat the
    incoming entry as a near-duplicate. Pure + side-effect free so the threshold
    is unit-testable without embeddings (tests/test_dedup.py)."""
    return similarity > DEDUP_SIMILARITY_THRESHOLD


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

        if is_duplicate_similarity(similarity):
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
