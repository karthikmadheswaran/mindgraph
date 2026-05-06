import json
import logging
import re
from datetime import datetime, timezone

from app.db import supabase
from app.llm import extract_text, flash
from app.services.ask_pipeline.date_format import format_entry_date, today_str
from app.services.ask_pipeline.state import AskState
from app.services.observability import langfuse_config

logger = logging.getLogger(__name__)

_DEFAULT_FALLBACK = {
    "query_types": ["semantic"],
    "time_range": None,
    "entities_mentioned": [],
    "dashboard_context_needed": False,
}


def _fetch_top_entities(user_id: str, limit: int = 50) -> list[dict]:
    result = (
        supabase.table("entities")
        .select("name, entity_type, mention_count")
        .eq("user_id", user_id)
        .gt("mention_count", 0)
        .order("mention_count", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _fetch_recent_entries(user_id: str, limit: int = 3) -> list[dict]:
    result = (
        supabase.table("entries")
        .select("auto_title, summary, created_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _format_entity_list(entities: list[dict]) -> str:
    if not entities:
        return "(no entities yet)"
    lines = []
    for e in entities:
        name = e.get("name") or ""
        etype = e.get("entity_type") or "unknown"
        count = e.get("mention_count") or 0
        lines.append(f"- {name} ({etype}, {count} mentions)")
    return "\n".join(lines)


def _format_recent_summaries(entries: list[dict], now: datetime) -> str:
    if not entries:
        return "(no recent entries)"
    lines = []
    for e in entries:
        date = format_entry_date(e["created_at"], now)
        title = (e.get("auto_title") or "Untitled").strip()
        summary = (e.get("summary") or "").strip()
        lines.append(f"- {date}: \"{title}\" — {summary}")
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_agent_json(raw: str) -> dict:
    cleaned = _strip_code_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("agent JSON must be an object")

    query_types = data.get("query_types") or []
    if not isinstance(query_types, list) or not query_types:
        query_types = ["semantic"]

    entities = data.get("entities_mentioned") or []
    if not isinstance(entities, list):
        entities = []

    return {
        "query_types": query_types,
        "time_range": data.get("time_range"),
        "entities_mentioned": entities,
        "dashboard_context_needed": bool(data.get("dashboard_context_needed", False)),
    }


def _build_prompt(question: str, today: str, entity_list: str, recent: str) -> str:
    return (
        "You are a query routing agent for a personal journal app.\n\n"
        "Given a user's question and their personal context, output a JSON routing decision.\n\n"
        f"Today's date: {today}\n\n"
        "Known entities in this user's journal:\n"
        f"{entity_list}\n\n"
        "Recent entries (last 3):\n"
        f"{recent}\n\n"
        "Output ONLY valid JSON matching this schema — no explanation, no markdown:\n"
        "{\n"
        "  \"query_types\": [\"temporal\" | \"semantic\" | \"recent\" | \"dashboard\" | \"keyword\"],\n"
        "  \"time_range\": {\"start\": \"YYYY-MM-DD\", \"end\": \"YYYY-MM-DD\"} | null,\n"
        "  \"entities_mentioned\": [{\"name\": \"...\", \"type\": \"...\"}],\n"
        "  \"dashboard_context_needed\": true | false\n"
        "}\n\n"
        "Rules:\n"
        "- query_types is an array — a question can be multiple types simultaneously\n"
        "- Use \"temporal\" when the question references a time period (month name, \"recently\", \"last week\", \"latest\", \"this month\")\n"
        "- Use \"recent\" when asking about latest activity with no specific time range\n"
        "- Use \"semantic\" for open-ended questions about topics, feelings, patterns\n"
        "- Use \"dashboard\" when asking about active projects, deadlines, current status\n"
        "- Use \"keyword\" when asking about a specific named entity or term\n"
        "- For entity disambiguation: use the known entities list to resolve ambiguous names\n"
        "- Always include today's date in your temporal reasoning\n\n"
        f"User question: {question.strip()}\n"
    )


async def query_understanding_agent(state: AskState) -> dict:
    now = datetime.now(timezone.utc)
    today = today_str(now)
    user_id = state["user_id"]

    entities = _fetch_top_entities(user_id, limit=50)
    recent_entries = _fetch_recent_entries(user_id, limit=3)

    prompt = _build_prompt(
        question=state["question"],
        today=today,
        entity_list=_format_entity_list(entities),
        recent=_format_recent_summaries(recent_entries, now),
    )

    try:
        response = await flash.ainvoke(prompt, config=langfuse_config())
        raw = extract_text(response)
        parsed = _parse_agent_json(raw)
    except Exception as exc:
        logger.warning(
            "query_understanding_agent fell back to default routing: %s",
            exc,
            exc_info=True,
        )
        parsed = dict(_DEFAULT_FALLBACK)

    return {
        "today_str": today,
        "query_types": parsed["query_types"],
        "time_range": parsed["time_range"],
        "entities_mentioned": parsed["entities_mentioned"],
        "dashboard_context_needed": parsed["dashboard_context_needed"],
    }
