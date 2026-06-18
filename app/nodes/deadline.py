import re
from app.state import JournalState, DeadlineNode
from datetime import datetime, date
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


# ---------------------------------------------------------------------------
# Past-event guard (deterministic "reliable-zero" backstop behind the prompt)
# ---------------------------------------------------------------------------
# The tense-gate prompt is a soft instruction; flash-lite (thinking_budget=0)
# still intermittently extracts past NARRATED actions ("I submitted my tax
# return", "went to the gym") as deadlines. This guard drops a deadline only when
# ALL of: (1) it is strictly past-dated vs the reference date, (2) it carries a
# completed past-action signal (irregular past verb or an -ed word), and (3) it
# has NO open-obligation cue. So overdue-but-open obligations ("still haven't
# sent it", "due ... by") and bare imperative obligations ("pay the bill on
# <date>", "dentist appointment on <date>") are KEPT — they lack a completed
# signal — and the guard does not over-correct on real (missed) deadlines.
# Measured (Vertex, N=5): pure-past leak 5/5 -> 0/5; overdue/future/missed-
# obligation/mixed fixtures all preserved 5/5. (evals/deadline_past_events_eval.py)
_OPEN_OBLIGATION_MARKERS = (
    "need to", "needs to", "have to", "has to", "must ", "haven't", "havent",
    "hasn't", "hasnt", "still ", "yet ", "due", "overdue", "pending",
    "to do", "to-do", " by ",
)
_IRREGULAR_PAST = (
    "went", "drank", "ate", "came", "woke", "felt", "did", "had", "was", "were",
    "got", "took", "made", "met", "rested", "played", "cooked", "sent", "skipped",
    "drove", "slept", "spent", "saw", "ran",
)
_IRREGULAR_PAST_RE = re.compile(r"\b(?:" + "|".join(_IRREGULAR_PAST) + r")\b")
_REGULAR_PAST_RE = re.compile(r"\b\w+ed\b")


def _has_open_obligation(text: str) -> bool:
    return any(marker in text for marker in _OPEN_OBLIGATION_MARKERS)


def _is_narrated_past_action(text: str) -> bool:
    return bool(_IRREGULAR_PAST_RE.search(text) or _REGULAR_PAST_RE.search(text))


def drop_past_event_deadlines(
    deadlines: list[DeadlineNode], reference_date: date
) -> list[DeadlineNode]:
    """Drop deadlines that are completed past-tense narration, not obligations.

    Scope: keys on ENGLISH past-tense morphology (-ed / irregular pasts). A
    precision filter for past-tense narration, NOT a universal past/future
    classifier. BLIND to: (1) present-tense narration of past events
    ("go to the arcade"), (2) non-English / transliterated entries, (3) bare
    noun+date phrases. FAILS SAFE — when it can't classify, the deadline passes
    through; it never drops a real obligation. Universal coverage requires the
    model-based (thinking-budget) approach — TRIGGER: warranted when real
    present-tense or non-English traffic makes the residual leak rate climb. Do
    NOT try to extend this guard with more language rules — it is fundamentally
    English-morphology-bound.
    """
    kept: list[DeadlineNode] = []
    for deadline in deadlines:
        due_at = deadline["due_at"]
        due_date = due_at.date() if isinstance(due_at, datetime) else due_at
        text = f"{deadline['description']} {deadline['raw_text']}".lower()
        is_past = isinstance(due_date, date) and due_date < reference_date
        if is_past and not _has_open_obligation(text) and _is_narrated_past_action(text):
            continue
        kept.append(deadline)
    return kept


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

A deadline is a FUTURE or still-pending obligation the writer MUST STILL act on — a task, payment, submission, meeting, appointment, or event that has not happened yet. Most journal text is past-tense narration of things that ALREADY happened; those are NOT deadlines, no matter how many dates they contain. When unsure, do NOT extract.

Reference Date:
{reference_date}

Cleaned Input:
{text}

Raw Input:
{raw_text}

Rules:
- TENSE GATE — apply FIRST to every candidate: include an item ONLY if it is something the writer STILL has to do (future or not-yet-done). If the sentence narrates something that ALREADY HAPPENED — past-tense verbs describing what someone did or how they felt (drank, cooked, went, met, woke, rested, played, was, felt, submitted, cleaned, "that's why I came") — it is a completed action or reflection: DROP it, even when it carries a resolved date.
- A merely OVERDUE task still to be done ("submit X by [a past date]", "pay the bill by [a past date]") is NOT a completed action — it IS a valid deadline; extract it. The test is completed-vs-pending, not whether the date is in the past.
- Urges, plans, and habits that were not turned into a concrete commitment are NOT deadlines: "I had an urge to play games", "I planned to go to the cafe on weekends", "I wanted to rest". Habitual/recurring phrases ("on weekends", "every Sunday") are not dated commitments. Judge tense from the writer's own verbs in the Raw Input, not from any date the Cleaned Input attached to a past sentence.
- A COMPLETED obligation is DONE, not a deadline, even though it uses a task verb: "I submitted the form", "I paid the bill", "I sent the email", "I renewed it" (past tense, already done) -> DROP. Only a not-yet-done obligation counts ("submit the form", "need to pay the bill", "have to renew it").
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
- "drank and cook on that day" / "I drank and 2026-06-13 I felt like a hangover"
  -> completed past activities, NOT deadlines.
- "went to the gaming cafe on Sunday" / "rotting until 4pm" / "came to a meeting, that's why I came"
  -> past events already happened, NOT deadlines.
- "on 2026-04-03 I felt more hopeful about life"
  -> past reflection with a date, NOT a deadline.
- [{{"description": "meeting with X", "due_at": "2026-04-09", "raw_text": "meeting tomorrow"}}, {{"description": "meeting with X", "due_at": "2026-04-09", "raw_text": "scheduled for tomorrow"}}]
  -> This is ONE event, extract it only once.

Output Rules:
- FINAL CHECK before returning: re-read each item's sentence — if it describes something that already happened, remove it. A purely past/reflective entry must return {{"deadlines": []}}.
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

    reference_date = datetime.strptime(
        resolve_reference_date(state.get("user_timezone", "UTC")), "%Y-%m-%d"
    ).date()
    deadlines = drop_past_event_deadlines(deadlines, reference_date)

    return {"deadline": deadlines}
