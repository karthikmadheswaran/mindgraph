import logging
from datetime import datetime, timezone

from app.ask_memory import extract_prior_user_messages
from app.db import supabase
from app.llm import flash
from app.schemas.pipeline import RoutingDecision
from app.services.ask_pipeline.date_format import format_entry_date, today_str
from app.services.ask_pipeline.state import AskState
from app.services.observability import langfuse_config

logger = logging.getLogger(__name__)

# Structured output: Gemini enforces the RoutingDecision shape (query_types and
# time_of_day are enum-constrained, time_range/entities are typed) via
# response_json_schema, so the agent no longer hand-parses JSON, strips code
# fences, or validates time_of_day. method="json_schema" is explicit.
_structured_flash = flash.with_structured_output(RoutingDecision, method="json_schema")

_DEFAULT_FALLBACK = {
    "query_types": ["semantic"],
    "time_range": None,
    "entities_mentioned": [],
    "dashboard_context_needed": False,
    "is_reask": False,
}

# How many prior USER turns the routing prompt sees for re-ask detection.
# User side only — assistant replies would bloat the prompt without helping
# the "did they already ask this" judgment.
_REASK_HISTORY_TURNS = 5


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


def _build_prompt(
    question: str,
    today: str,
    entity_list: str,
    recent: str,
    prior_user_turns: list[str] | None = None,
) -> str:
    history_section = ""
    if prior_user_turns:
        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(prior_user_turns, 1))
        history_section = (
            "Earlier user messages in this conversation (oldest first; assistant replies omitted):\n"
            f"{numbered}\n\n"
        )
    return (
        "You are a query routing agent for a personal journal app.\n\n"
        "Given a user's question and their personal context, output a JSON routing decision.\n\n"
        f"Today's date: {today}\n\n"
        "Known entities in this user's journal:\n"
        f"{entity_list}\n\n"
        "Recent entries (last 3):\n"
        f"{recent}\n\n"
        f"{history_section}"
        "Produce a routing decision with these fields:\n"
        "- query_types: array of \"temporal\" | \"semantic\" | \"recent\" | \"dashboard\" | \"keyword\"\n"
        "- time_range: {start: \"YYYY-MM-DD\" (inclusive), end: \"YYYY-MM-DD\" (inclusive), "
        "time_of_day: \"morning\" | \"afternoon\" | \"evening\" | \"night\" | null} or null\n"
        "- entities_mentioned: array of {name, type}\n"
        "- dashboard_context_needed: true | false\n"
        "- is_reask: true | false\n\n"
        "Rules:\n"
        "- query_types is an array — a question can be multiple types simultaneously\n"
        "- Use \"temporal\" when the question references a time period (month name, \"recently\", \"last week\", \"latest\", \"this month\")\n"
        "- Use \"recent\" when asking about latest activity with no specific time range\n"
        "- Use \"semantic\" for open-ended questions about topics, feelings, patterns\n"
        "- Use \"dashboard\" when asking about active projects, deadlines, current status\n"
        "- Use \"keyword\" when asking about a specific named entity or term\n"
        "- For entity disambiguation: use the known entities list to resolve ambiguous names\n"
        "- Always include today's date in your temporal reasoning\n\n"
        "Time-of-day rules:\n"
        "- Set time_range.time_of_day ONLY when the user EXPLICITLY references a time of day:\n"
        "    \"morning of May 11th\"           → time_of_day=\"morning\"\n"
        "    \"what did I write last night\"   → time_of_day=\"night\"\n"
        "    \"evening reflections\"           → time_of_day=\"evening\"\n"
        "    \"this afternoon\"                → time_of_day=\"afternoon\"\n"
        "- LEAVE time_of_day NULL for general date queries (no explicit time-of-day word):\n"
        "    \"what happened on May 11\"        → time_of_day=null\n"
        "    \"anything from last week\"        → time_of_day=null\n"
        "    \"my entries from yesterday\"      → time_of_day=null\n"
        "- DO NOT infer time_of_day from question TOPIC. \"morning routine\", \"good morning\",\n"
        "  \"night owl\" are about the topic, not about when the entry was written\n"
        "  → time_of_day=null\n"
        "- Canonical labels only: \"morning\" | \"afternoon\" | \"evening\" | \"night\". Anything\n"
        "  else (\"dawn\", \"midday\", \"late night\") → pick the nearest canonical label.\n\n"
        "Re-ask rules:\n"
        "- Set is_reask=true when the current question asks for substantially the SAME information\n"
        "  as an earlier user message in this conversation. This includes rephrasings, \"again\",\n"
        "  \"one more time\", \"you already said that\", requests to simplify or repeat what was\n"
        "  already given, and frustrated repeats.\n"
        "- Set is_reask=false for genuine follow-ups that NARROW or EXTEND an earlier question —\n"
        "  \"which of those is first?\", \"tell me more about that\", \"can you add X to that list?\"\n"
        "  are follow-ups, NOT re-asks.\n"
        "- Set is_reask=false for new topics.\n"
        "- If no earlier user messages are listed above, is_reask MUST be false.\n\n"
        f"User question: {question.strip()}\n"
    )


async def query_understanding_agent(state: AskState) -> dict:
    now = datetime.now(timezone.utc)
    today = today_str(now)
    user_id = state["user_id"]

    entities = _fetch_top_entities(user_id, limit=50)
    recent_entries = _fetch_recent_entries(user_id, limit=3)
    prior_user_turns = extract_prior_user_messages(
        state.get("conversation_history") or ""
    )[-_REASK_HISTORY_TURNS:]

    prompt = _build_prompt(
        question=state["question"],
        today=today,
        entity_list=_format_entity_list(entities),
        recent=_format_recent_summaries(recent_entries, now),
        prior_user_turns=prior_user_turns,
    )

    # Keep a try/except around the API call as a safety net: on an API failure
    # (or any rare schema-validation error) fall back to default routing rather
    # than 500-ing the Ask request. Structured output removes the JSON-parse
    # failure mode the old fallback mainly guarded against.
    try:
        result = await _structured_flash.ainvoke(prompt, config=langfuse_config())
        parsed = {
            "query_types": result.query_types,
            "time_range": result.time_range.model_dump() if result.time_range else None,
            "entities_mentioned": [
                {"name": e.name, "type": e.type} for e in result.entities_mentioned
            ],
            "dashboard_context_needed": result.dashboard_context_needed,
            # No prior user turns shown → the model never saw evidence of a
            # re-ask; force false regardless of what it emitted.
            "is_reask": bool(result.is_reask) if prior_user_turns else False,
        }
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
