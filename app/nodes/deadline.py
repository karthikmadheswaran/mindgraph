from app.state import JournalState, DeadlineNode
from datetime import datetime
from zoneinfo import ZoneInfo

from app.llm import flash as model
from app.schemas.pipeline import DeadlineList

USE_SEMANTIC_VALIDATOR = False

# Structured output: Gemini enforces the DeadlineList shape, including the ISO
# due_at format via the schema's regex pattern. The strptime datetime coercion,
# the (disabled) bad-phrase semantic validator, and dedup_deadlines all stay as
# Python post-processing in the node. method="json_schema" is explicit.
structured_model = model.with_structured_output(DeadlineList, method="json_schema")


def resolve_reference_date(user_timezone: str) -> str:
    try:
        timezone = ZoneInfo(user_timezone or "UTC")
    except Exception:
        timezone = ZoneInfo("UTC")

    return datetime.now(timezone).strftime("%Y-%m-%d")


def normalize_deadline_description(description: str) -> str:
    return " ".join(str(description or "").strip().lower().split())


def make_deadline_date_key(due_at) -> str:
    if isinstance(due_at, datetime):
        return due_at.date().isoformat()

    value = str(due_at or "").strip()
    if "T" in value:
        return value.split("T", 1)[0]
    return value


def prefer_deadline_candidate(existing: DeadlineNode, candidate: DeadlineNode) -> DeadlineNode:
    existing_desc = normalize_deadline_description(existing["description"])
    candidate_desc = normalize_deadline_description(candidate["description"])

    if len(candidate_desc) < len(existing_desc):
        return candidate
    if len(existing_desc) < len(candidate_desc):
        return existing

    existing_raw = " ".join(existing["raw_text"].strip().split())
    candidate_raw = " ".join(candidate["raw_text"].strip().split())
    return candidate if len(candidate_raw) > len(existing_raw) else existing


def dedup_deadlines(deadlines: list[DeadlineNode]) -> list[DeadlineNode]:
    exact_deduped: dict[tuple[str, str], DeadlineNode] = {}

    for deadline in deadlines:
        key = (
            normalize_deadline_description(deadline["description"]),
            make_deadline_date_key(deadline["due_at"]),
        )

        existing = exact_deduped.get(key)
        if existing is None:
            exact_deduped[key] = deadline
            continue

        exact_deduped[key] = prefer_deadline_candidate(existing, deadline)

    unique: list[DeadlineNode] = []

    for deadline in sorted(
        exact_deduped.values(),
        key=lambda item: (
            make_deadline_date_key(item["due_at"]),
            len(normalize_deadline_description(item["description"])),
            normalize_deadline_description(item["description"]),
        ),
    ):
        deadline_desc = normalize_deadline_description(deadline["description"])
        deadline_date = make_deadline_date_key(deadline["due_at"])
        merged = False

        for index, existing in enumerate(unique):
            existing_desc = normalize_deadline_description(existing["description"])
            existing_date = make_deadline_date_key(existing["due_at"])

            if deadline_date != existing_date:
                continue

            if deadline_desc in existing_desc or existing_desc in deadline_desc:
                unique[index] = prefer_deadline_candidate(existing, deadline)
                merged = True
                break

        if not merged:
            unique.append(deadline)

    return unique


def build_deadline_prompt(text: str, raw_text: str, user_timezone: str) -> str:
    reference_date = resolve_reference_date(user_timezone)
    return f"""
You are a strict deadline extraction engine.

Extract only concrete deadlines or scheduled commitments.

Reference Date:
{reference_date}

Cleaned Input:
{text}

Raw Input:
{raw_text}

Rules:
- Extract only if there is a clear time reference.
- The time reference must be tied to a real task, obligation, meeting, payment, submission, appointment, or event.
- Do not extract hopes, vague future thoughts, reflections, metadata dates, or project/status phrases.
- Do not invent deadlines that are not in the text.
- If the same event is mentioned multiple times, extract it only once. Do not create separate items for repeated references to the same event on the same date.
- If a date is ambiguous and cannot be resolved confidently, skip it.

Do NOT extract examples like:
- new possibilities
- hope for a better day
- entry date
- project progress
- [{{"description": "meeting with X", "due_at": "2026-04-09", "raw_text": "meeting tomorrow"}}, {{"description": "meeting with X", "due_at": "2026-04-09", "raw_text": "scheduled for tomorrow"}}]
  -> This is ONE event, extract it only once.

Output Rules:
- Return all deadlines under a "deadlines" key.
- If no deadlines exist, return {{"deadlines": []}}.
- Use exactly these keys for each item: "description", "due_at", "raw_text"
- "description" = short description of what the deadline is for
- "due_at" = date in YYYY-MM-DD format, or datetime in YYYY-MM-DDTHH:MM format if a specific time is mentioned. Use YYYY-MM-DD when no time is mentioned.
- Do not invent times - only include a time if the original text explicitly states one.
- "raw_text" = the exact deadline phrase from the journal text
- Resolve relative dates using the Reference Date.
- Do not include extra fields.

Format:
{{"deadlines": [
  {{"description": "submit visa documents", "due_at": "2026-04-10", "raw_text": "by Friday"}},
  {{"description": "meeting with Manuel", "due_at": "2026-04-09T19:30", "raw_text": "meeting at 19:30 today"}}
]}}
""".strip()


def is_valid_deadline_candidate(
    description: str,
    raw_text: str,
    raw_source_text: str,
    cleaned_source_text: str,
) -> bool:
    description_l = description.lower().strip()
    raw_text_l = raw_text.lower().strip()
    raw_source_l = raw_source_text.lower()
    cleaned_source_l = cleaned_source_text.lower()

    if not description_l or not raw_text_l:
        return False

    bad_phrases = [
        "new possibilities",
        "hope for a better day",
        "entry date",
        "project progress",
    ]

    for phrase in bad_phrases:
        if phrase in description_l or phrase in raw_text_l:
            return False

    # raw_text can appear either in original user text or normalized cleaned text
    if raw_text_l not in raw_source_l and raw_text_l not in cleaned_source_l:
        return False

    return True


def validate_deadlines(
    items: list[dict],
    raw_source_text: str,
    cleaned_source_text: str,
) -> list[DeadlineNode]:
    """Apply the post-processing the response schema can't express: the
    (disabled) bad-phrase semantic validator and strptime datetime coercion.
    The schema already guarantees the ISO due_at format and required keys."""
    valid: list[DeadlineNode] = []

    for item in items:
        description = (item.get("description") or "").strip()
        due_at = (item.get("due_at") or "").strip()
        extracted_raw_text = (item.get("raw_text") or "").strip()

        if not description:
            continue

        if USE_SEMANTIC_VALIDATOR and not is_valid_deadline_candidate(
            description,
            extracted_raw_text,
            raw_source_text,
            cleaned_source_text,
        ):
            continue

        due_at_dt = None
        for datetime_format in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                due_at_dt = datetime.strptime(due_at, datetime_format)
                break
            except ValueError:
                continue

        if due_at_dt is None:
            continue

        valid.append(
            {
                "description": description,
                "due_at": due_at_dt,
                "raw_text": extracted_raw_text,
            }
        )

    return valid


async def extract_deadlines(state: JournalState) -> dict:
    text = state["cleaned_text"]
    raw_text = state["raw_text"]

    prompt = build_deadline_prompt(text, raw_text, state.get("user_timezone", "UTC"))
    result = await structured_model.ainvoke(prompt)
    items = [deadline.model_dump() for deadline in result.deadlines]

    deadlines = validate_deadlines(
        items,
        raw_source_text=raw_text,
        cleaned_source_text=text,
    )
    deadlines = dedup_deadlines(deadlines)

    return {"deadline": deadlines}
