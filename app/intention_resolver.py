# app/intention_resolver.py
"""Resolve candidate stated-intentions against the persistent intentions table
and persist them (drift P2). Called from store_node, alongside resolve_entities.

The P1 node (app/nodes/intentions.py) writes candidate intentions to
state['intentions']. This step decides, per candidate, whether it is a NEW
intention or a RE-REFERENCE of one the user already stated — and it is the step
that winds the drift clock (last_referenced_at). Mirrors resolve_entities:
extraction produced candidates; store resolves them against the DB and persists,
bumping a re-reference's last_referenced_at / reference_count the way entity
resolution bumps mention_count / last_seen_at.

Bias-to-split, idempotency, and fail-safe-per-candidate are deliberate — see the
inline notes; they are lessons already paid for elsewhere in the pipeline.
"""
import json
import logging
import math
from datetime import datetime, timezone

from app.db import supabase
from app.embeddings import get_embedding

logger = logging.getLogger(__name__)

# Cosine cutoff for treating a candidate as a RE-REFERENCE of an existing
# intention (>= => same; below => new). Calibrated in
# evals/intention_threshold_calibration.py.
#
# BIAS TO SPLIT (deliberately high). A false MERGE silently destroys a real
# intention — it folds into another row, invisible and unrecoverable from the
# user's view. A false SPLIT only makes a visible duplicate card the user can
# dismiss. So the threshold sits ABOVE the observed distinct-intention max: when
# unsure, treat as new. Same reasoning as the entry-dedup 0.92 bias.
#
# Calibration (2026-06-19): distinct (should-split) pairs maxed at 0.8227; true
# restatements clustered 0.91–0.96. Thresholds 0.84–0.916 are an identical
# plateau on the fixtures (0 false merges, 1 false split, 11/12 restatements
# merged). 0.90 is the top of that plateau — maximal margin (0.077) above the
# distinct max against the unrecoverable false-merge, before 0.92 starts
# sacrificing real restatements. Chosen over the auto-recommended 0.84 for that
# safety margin.
INTENTION_MATCH_THRESHOLD = 0.90


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _vec(value):
    """Stored pgvector reads back as a JSON string from Supabase; the in-memory
    test fake stores a list. Accept both."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


def _is_duplicate_constraint_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "23505" in msg or "duplicate key value violates unique constraint" in msg


def _entry_created_at(entry_id) -> str:
    """The source entry's created_at drives first_stated_at / last_referenced_at
    — NOT now(). This is what lets the P3 backfill produce REAL historical dates
    (a months-old intention reads as months-old drift, not day-0)."""
    try:
        resp = (
            supabase.table("entries")
            .select("created_at")
            .eq("id", entry_id)
            .limit(1)
            .execute()
        )
        if resp.data and resp.data[0].get("created_at"):
            return resp.data[0]["created_at"]
    except Exception as exc:
        logger.warning("intentions: could not read entry %s created_at: %s", entry_id, exc)
    return datetime.now(timezone.utc).isoformat()


def _best_match(embedding, existing: list[dict]):
    best, best_sim = None, 0.0
    for row in existing:
        vec = _vec(row.get("embedding"))
        if not vec:
            continue
        sim = _cosine(embedding, vec)
        if sim > best_sim:
            best, best_sim = row, sim
    return best, best_sim


async def resolve_and_persist_intentions(entry_id, intentions: list[dict], user_id: str) -> dict:
    """For each candidate intention: re-reference an existing active/dormant
    intention if cosine >= INTENTION_MATCH_THRESHOLD, else insert a new one.
    Returns counts. Never raises on a single bad candidate — store_node processes
    the whole entry and one intention must not sink it (the P1 None-guard lesson)."""
    if not intentions:
        return {"inserted": 0, "rereferenced": 0, "skipped": 0}

    entry_created_at = _entry_created_at(entry_id)

    existing_resp = (
        supabase.table("intentions")
        .select("id, text, embedding, status, reference_count, source_entry_id")
        .eq("user_id", user_id)
        .in_("status", ["active", "dormant"])
        .is_("deleted_at", "null")
        .execute()
    )
    existing = existing_resp.data or []

    inserted = rereferenced = skipped = 0

    for candidate in intentions:
        text = (candidate.get("text") or "").strip()
        if not text:
            continue
        try:
            embedding = await get_embedding(text)
            best, best_sim = _best_match(embedding, existing)

            if best is not None and best_sim >= INTENTION_MATCH_THRESHOLD:
                # Reprocess of the ORIGIN entry: the candidate matches the row it
                # itself first stated. No-op so reference_count / last_referenced
                # stay idempotent on re-runs.
                if best.get("source_entry_id") == entry_id:
                    skipped += 1
                    continue
                update = {
                    "last_referenced_at": entry_created_at,
                    "reference_count": (best.get("reference_count") or 1) + 1,
                }
                if best.get("status") == "dormant":
                    update["status"] = "active"  # a re-reference revives it
                supabase.table("intentions").update(update).eq("id", best["id"]).execute()
                best.update(update)  # so later candidates in THIS entry see the bump
                rereferenced += 1
                continue

            row = {
                "user_id": user_id,
                "text": text,
                "embedding": embedding,
                "status": "active",
                "source_entry_id": entry_id,
                "first_stated_at": entry_created_at,
                "last_referenced_at": entry_created_at,
                "reference_count": 1,
            }
            resp = supabase.table("intentions").insert(row).execute()
            if resp.data:
                inserted += 1
                stored = dict(row)
                stored["id"] = resp.data[0].get("id")
                existing.append(stored)  # a later near-dup candidate can re-ref it
        except Exception as exc:
            # Partial unique (user_id, source_entry_id, lower(text)) WHERE
            # deleted_at IS NULL: reprocessing re-inserts the same text -> 23505.
            # Treat as a no-op, like store_entry_deadlines. Any other error on one
            # candidate is logged and skipped — never crash the entry.
            if _is_duplicate_constraint_error(exc):
                skipped += 1
                continue
            logger.warning("intentions: persist failed for %r; skipping: %s", text, exc, exc_info=True)
            skipped += 1
            continue

    logger.info(
        "Intentions resolved: inserted=%d rereferenced=%d skipped=%d",
        inserted, rereferenced, skipped,
    )
    return {"inserted": inserted, "rereferenced": rereferenced, "skipped": skipped}
