import logging

from app.services.ask_pipeline.state import AskState
from app.services.ask_service import is_deadline_query
from app.services.deadline_service import list_deadlines
from app.services.project_service import list_projects

logger = logging.getLogger(__name__)

# Statuses surfaced to Ask for deadline-list queries. pending = upcoming,
# snoozed = deferred-but-live, missed = OVERDUE (mark_overdue_deadlines_as_missed
# flips overdue pending rows to missed before the read, so "am I behind" can only
# be answered if missed is included here — the original bug was status=None
# defaulting to pending-only). "done" is deliberately excluded: "what's due" /
# "am I behind" never want completed deadlines.
_ASK_DEADLINE_STATUSES = "pending,snoozed,missed"


def _format_deadline(d: dict) -> str:
    """Status-tagged so the model can answer 'am I behind' without re-deriving
    status from raw dates. Date trimmed to the ISO day (drop time/offset noise)."""
    description = (d.get("description") or "").strip() or "Untitled deadline"
    due = (d.get("due_date") or "").strip()
    if not due:
        return description
    due_date = due[:10]
    status = (d.get("status") or "").strip().lower()
    if status == "missed":
        return f"{description} — was due {due_date} (overdue)"
    if status == "snoozed":
        return f"{description} — due {due_date} (snoozed)"
    return f"{description} — due {due_date} (pending)"


async def dashboard_context(state: AskState) -> dict:
    # Fire when EITHER the LLM router asked for dashboard context OR the
    # deterministic deadline heuristic matched. The heuristic backstops two router
    # failure modes: the LLM not setting dashboard_context_needed on a clear
    # deadline query, and query_types collapsing to {"temporal"} (which makes
    # hybrid_rag self-skip). GUARDRAIL: the fetch stays GATED — it does NOT run for
    # every query — so dashboard_has_results can't falsely mark an off-topic query
    # high-confidence and defeat the honest-refusal path (see _compute_low_confidence).
    question = state.get("question") or ""
    if not (state.get("dashboard_context_needed") or is_deadline_query(question)):
        return {}

    try:
        projects_result = await list_projects(status=None, user_id=state["user_id"])
        deadlines_result = await list_deadlines(
            status=_ASK_DEADLINE_STATUSES, user_id=state["user_id"]
        )
    except Exception as exc:
        logger.warning("dashboard_context fetch failed: %s", exc, exc_info=True)
        return {"dashboard_context": {}, "dashboard_has_results": False}

    project_names = [
        (p.get("name") or "").strip()
        for p in (projects_result.get("projects") or [])
        if p.get("name")
    ]
    deadline_strings = [
        _format_deadline(d)
        for d in (deadlines_result.get("deadlines") or [])
    ]

    has_results = bool(project_names) or bool(deadline_strings)
    return {
        "dashboard_context": {
            "projects": project_names,
            "deadlines": deadline_strings,
        },
        "dashboard_has_results": has_results,
    }
