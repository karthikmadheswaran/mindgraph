import logging
import os

from app.services.ask_pipeline.state import AskState
from app.services.ask_service import HIGH_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)

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

    return {
        "assembled_context": "\n".join(parts).strip(),
        "is_low_confidence": is_low_confidence,
    }
