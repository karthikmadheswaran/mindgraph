import logging
import math
from datetime import datetime, timezone

from app.services.ask_pipeline.date_format import _parse_iso, format_entry_date
from app.services.ask_pipeline.state import AskState
from app.services.ask_service import (
    MAX_CONTEXT_ENTRIES,
    MAX_CONTEXT_ENTRIES_BROAD,
    get_relevance_label,
    get_relevance_label_reranked,
    is_broad_query,
    retrieve_relevant_entries,
)

logger = logging.getLogger(__name__)

LAMBDA_DECAY = 0.01


def apply_recency_decay(
    candidates: list[dict],
    now: datetime,
    lambda_decay: float = LAMBDA_DECAY,
) -> list[dict]:
    for entry in candidates:
        created_at = entry.get("created_at")
        if not created_at:
            entry["adjusted_score"] = entry.get("_rerank_score", 0.0) or 0.0
            continue
        try:
            dt = _parse_iso(created_at)
        except Exception:
            entry["adjusted_score"] = entry.get("_rerank_score", 0.0) or 0.0
            continue
        days_ago = max(0, (now - dt).days)
        base_score = entry.get("_rerank_score")
        if base_score is None:
            base_score = entry.get("similarity", 0.0) or 0.0
        decay_multiplier = math.exp(-lambda_decay * days_ago)
        entry["adjusted_score"] = float(base_score) * decay_multiplier
    return sorted(candidates, key=lambda e: e.get("adjusted_score", 0.0), reverse=True)


def _label_for(entry: dict) -> str:
    if "_rerank_score" in entry:
        return get_relevance_label_reranked(entry["_rerank_score"])
    sim = entry.get("similarity", 0.0) or entry.get("_vector_sim", 0.0) or 0.0
    return entry.get("relevance") or get_relevance_label(sim)


async def hybrid_rag(
    state: AskState,
    *,
    lambda_decay: float = LAMBDA_DECAY,
) -> dict:
    query_types = state.get("query_types") or []
    if query_types and set(query_types) == {"temporal"}:
        return {}

    candidates = await retrieve_relevant_entries(
        question=state["question"],
        user_id=state["user_id"],
        history_messages=None,
    )
    if not candidates:
        return {"rag_entries": [], "rag_max_similarity": 0.0}

    now = datetime.now(timezone.utc)
    decayed = apply_recency_decay(candidates, now, lambda_decay=lambda_decay)

    max_entries = (
        MAX_CONTEXT_ENTRIES_BROAD
        if is_broad_query(state["question"])
        else MAX_CONTEXT_ENTRIES
    )
    final = decayed[:max_entries]

    entries = []
    for entry in final:
        text = (
            entry.get("cleaned_text")
            or entry.get("raw_text")
            or entry.get("summary")
            or ""
        )
        entries.append(
            {
                "id": entry.get("id"),
                "title": (entry.get("auto_title") or "Untitled").strip(),
                "raw_text": text.strip(),
                "date": format_entry_date(entry["created_at"], now)
                if entry.get("created_at")
                else "Unknown date",
                "relevance": _label_for(entry),
                "rerank_score": entry.get("_rerank_score"),
                "adjusted_score": entry.get("adjusted_score"),
                "created_at": entry.get("created_at"),
            }
        )

    # Confidence signal: top original cosine similarity across returned entries.
    # Use vector similarity (not rerank score) so the value lives in the same
    # space as MIN_SIMILARITY / HIGH_CONFIDENCE_THRESHOLD. BM25-only entries
    # have _vector_sim=0, which is exactly what we want — they shouldn't push
    # the confidence signal up on their own.
    max_similarity = 0.0
    for entry in final:
        sim = entry.get("_vector_sim") or entry.get("similarity") or 0.0
        if sim > max_similarity:
            max_similarity = float(sim)

    logger.info(
        "hybrid_rag: %d entries (lambda=%.4f, max=%d, max_sim=%.3f)",
        len(entries),
        lambda_decay,
        max_entries,
        max_similarity,
    )
    return {"rag_entries": entries, "rag_max_similarity": max_similarity}
