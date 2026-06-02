import logging
import os

from app.db import supabase
from app.embeddings import get_embedding
from app.entity_resolver import base_normalize, should_accept_semantic_match
from app.services.ask_pipeline.state import AskState
from app.services.ask_service import HIGH_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

# Vivek-class entity filtering (advisory mode). Only "high-signal" entity
# mentions are checked: types that name a concrete referent the user could have
# written about, and long enough not to be a stray initial ("V"). Loose topical
# nouns aren't gated because their absence doesn't imply a hallucination.
HIGH_SIGNAL_ENTITY_TYPES = frozenset({"person", "place", "organization"})
_MIN_ENTITY_NAME_LEN = 3
# Mirrors the semantic gate in resolve_entities but slightly stricter (0.85 vs
# 0.8): this is an existence probe, so we'd rather miss than falsely "find" an
# entity and suppress the advisory signal.
_ENTITY_CHECK_SIM_THRESHOLD = 0.85

# Runtime override mirrors MIN_SIMILARITY pattern — lets evals sweep the
# threshold without committing changes.
_HIGH_CONFIDENCE_OVERRIDE = os.environ.get("RAG_EVAL_HIGH_CONFIDENCE")
EFFECTIVE_HIGH_CONFIDENCE = (
    float(_HIGH_CONFIDENCE_OVERRIDE)
    if _HIGH_CONFIDENCE_OVERRIDE
    else HIGH_CONFIDENCE_THRESHOLD
)


def _compute_low_confidence(state: AskState) -> bool:
    """
    Refuse if no branch produced a real, on-topic match.

    recent_summaries is excluded — it's an always-on baseline (last N entries
    regardless of query), so it can't corroborate relevance. The signal is:
      - hybrid_rag with max_similarity at or above the high-confidence ceiling, OR
      - temporal_retrieval finding entries in a resolved date range, OR
      - dashboard_context returning projects/deadlines for a dashboard-shaped query.
    If none of those fire, generation should refuse.
    """
    rag_entries = state.get("rag_entries") or []
    rag_max_sim = float(state.get("rag_max_similarity") or 0.0)
    rag_confident = bool(rag_entries) and rag_max_sim >= EFFECTIVE_HIGH_CONFIDENCE

    temporal_has_results = bool(state.get("temporal_has_results"))
    dashboard_has_results = bool(state.get("dashboard_has_results"))

    return not (rag_confident or temporal_has_results or dashboard_has_results)


def _filter_high_signal_entities(entities_mentioned: list[dict]) -> list[dict]:
    out: list[dict] = []
    for e in entities_mentioned or []:
        name = (e.get("name") or "").strip()
        etype = (e.get("type") or "").strip().lower()
        if etype in HIGH_SIGNAL_ENTITY_TYPES and len(name) >= _MIN_ENTITY_NAME_LEN:
            out.append({"name": name, "type": etype})
    return out


async def _entity_exists(name: str, etype: str, user_id: str) -> dict:
    """Probe whether a single high-signal entity exists in the user's data.

    Exact base_normalize match first (cheap), semantic fallback second, gated by
    should_accept_semantic_match. Returns a per-entity outcome dict for logging.
    """
    incoming_base = base_normalize(name)
    rows = (
        supabase.table("entities")
        .select("name, entity_type")
        .eq("user_id", user_id)
        .eq("entity_type", etype)
        .execute()
    ).data or []
    for row in rows:
        if base_normalize(row.get("name", "")) == incoming_base:
            return {
                "name": name,
                "type": etype,
                "matched": True,
                "method": "exact",
                "matched_name": row.get("name"),
                "similarity": None,
            }

    try:
        embedding = await get_embedding(name)
        res = supabase.rpc(
            "match_entities",
            {
                "query_embedding": embedding,
                "match_count": 3,
                "filter_user_id": user_id,
                "similarity_threshold": _ENTITY_CHECK_SIM_THRESHOLD,
                "filter_entity_type": etype,
            },
        ).execute()
        candidates = res.data or []
        for cand in candidates:
            sim = float(cand.get("similarity") or 0.0)
            if should_accept_semantic_match(name, cand.get("name", ""), sim):
                return {
                    "name": name,
                    "type": etype,
                    "matched": True,
                    "method": "semantic",
                    "matched_name": cand.get("name"),
                    "similarity": round(sim, 3),
                }
        top_sim = round(float(candidates[0]["similarity"]), 3) if candidates else None
        return {
            "name": name,
            "type": etype,
            "matched": False,
            "method": "none",
            "matched_name": None,
            "similarity": top_sim,
        }
    except Exception as exc:
        # Never let the advisory probe break the Ask request — fall back to
        # "unknown" (treated as miss) and record the error for review.
        logger.warning("entity existence probe failed for %r: %s", name, exc)
        return {
            "name": name,
            "type": etype,
            "matched": False,
            "method": "error",
            "matched_name": None,
            "similarity": None,
        }


async def _check_question_entities(state: AskState) -> tuple[bool | None, dict]:
    """Returns (question_entity_known, details).

    None  -> check skipped (no high-signal entities in the question)
    True  -> at least one high-signal entity exists in the user's data
    False -> all high-signal entities miss (Vivek-class: likely hallucination)
    """
    entities_mentioned = state.get("entities_mentioned") or []
    high_signal = _filter_high_signal_entities(entities_mentioned)
    if not high_signal:
        return None, {
            "high_signal_entities": [],
            "results": [],
            "reason": "no high-signal entities",
        }

    user_id = state["user_id"]
    results = [await _entity_exists(e["name"], e["type"], user_id) for e in high_signal]
    known = any(r["matched"] for r in results)
    return known, {"high_signal_entities": high_signal, "results": results}


async def context_assembler(state: AskState) -> dict:
    parts: list[str] = []

    today = state.get("today_str") or ""
    if today:
        parts.append(f"Today is {today}.")

    recent = state.get("recent_summaries") or []
    if recent:
        parts.append("\n# Recent journal activity")
        for s in recent:
            title = (s.get("title") or "Untitled").strip()
            summary = (s.get("summary") or "").strip()
            parts.append(f"- {s['date']}: \"{title}\" — {summary}")

    temporal = state.get("temporal_entries") or []
    if temporal:
        parts.append("\n# Journal entries from the requested time period")
        for e in temporal:
            title = (e.get("title") or "Untitled").strip()
            text = (e.get("raw_text") or e.get("summary") or "").strip()
            parts.append(f"Entry ({e['date']}, title: {title}):\n{text}\n---")

    rag = state.get("rag_entries") or []
    if rag:
        parts.append("\n# Retrieved journal entries (relevance-tagged)")
        for e in rag:
            relevance = e.get("relevance") or "unknown"
            text = (e.get("raw_text") or "").strip()
            parts.append(f"Entry ({e['date']}, relevance: {relevance}):\n{text}\n---")

    dashboard = state.get("dashboard_context") or {}
    projects = dashboard.get("projects") or []
    deadlines = dashboard.get("deadlines") or []
    if projects or deadlines:
        parts.append("\n# Current dashboard context")
        parts.append(
            f"Active projects: {', '.join(projects) if projects else '(none)'}"
        )
        parts.append(
            f"Upcoming deadlines: {', '.join(deadlines) if deadlines else '(none)'}"
        )

    is_low_confidence = _compute_low_confidence(state)
    if is_low_confidence:
        logger.info(
            "context_assembler: is_low_confidence=True "
            "(rag_max_sim=%.3f threshold=%.3f temporal=%s dashboard=%s)",
            float(state.get("rag_max_similarity") or 0.0),
            EFFECTIVE_HIGH_CONFIDENCE,
            bool(state.get("temporal_has_results")),
            bool(state.get("dashboard_has_results")),
        )

    # ── Vivek-class entity filtering: ADVISORY MODE ──────────────────────────
    # Compute the would-be gate decision with the entity-existence signal mixed
    # in, but DO NOT use it to gate generation. is_low_confidence above is
    # unchanged. We log when the entity check would have flipped the outcome so
    # we can measure the false-positive rate before promoting to active refusal.
    question_entity_known, check_details = await _check_question_entities(state)
    is_low_confidence_with_check = is_low_confidence or (
        question_entity_known is False
    )
    would_have_changed_outcome = is_low_confidence_with_check != is_low_confidence

    logger.info(
        "entity_check_advisory",
        extra={
            "trace_id": state.get("trace_id"),
            "user_id": state.get("user_id"),
            "question": (state.get("question") or "")[:200],
            "entities_mentioned": state.get("entities_mentioned") or [],
            "high_signal_entities": check_details.get("high_signal_entities"),
            "entities_known_status": check_details.get("results"),
            "is_low_confidence_current": is_low_confidence,
            "is_low_confidence_with_check": is_low_confidence_with_check,
            "would_have_changed_outcome": would_have_changed_outcome,
        },
    )

    return {
        "assembled_context": "\n".join(parts).strip(),
        "is_low_confidence": is_low_confidence,
        "question_entity_known": question_entity_known,
        "question_entity_check_details": check_details,
    }
