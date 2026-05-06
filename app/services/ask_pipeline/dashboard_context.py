import logging

from app.services.ask_pipeline.state import AskState
from app.services.deadline_service import list_deadlines
from app.services.project_service import list_projects

logger = logging.getLogger(__name__)


def _format_deadline(d: dict) -> str:
    description = (d.get("description") or "").strip() or "Untitled deadline"
    due = (d.get("due_date") or "").strip()
    return f"{description} ({due})" if due else description


async def dashboard_context(state: AskState) -> dict:
    if not state.get("dashboard_context_needed"):
        return {}

    try:
        projects_result = await list_projects(status=None, user_id=state["user_id"])
        deadlines_result = await list_deadlines(status=None, user_id=state["user_id"])
    except Exception as exc:
        logger.warning("dashboard_context fetch failed: %s", exc, exc_info=True)
        return {"dashboard_context": {}}

    project_names = [
        (p.get("name") or "").strip()
        for p in (projects_result.get("projects") or [])
        if p.get("name")
    ]
    deadline_strings = [
        _format_deadline(d)
        for d in (deadlines_result.get("deadlines") or [])
    ]

    return {
        "dashboard_context": {
            "projects": project_names,
            "deadlines": deadline_strings,
        }
    }
