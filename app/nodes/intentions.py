"""extract_intentions — pull STATED INTENTIONS from entry prose (drift P1).

A stated intention is an UNDATED aspiration the writer expresses a present,
first-person want/intent to do but is NOT yet doing ("I want to get back to the
gym", "I keep meaning to learn Spanish"). It is the bottom-up goal drift
detection tracks over time. It is NOT a deadline (dated obligation — that's the
deadline node's job), NOT past narration, and NOT already-acting (that's a drift
RESOLUTION signal, handled in P2, not a new intention).

Mirrors app/nodes/deadline.py: flash-lite (thinking_budget=0) structured output,
the deadline prompt's "when unsure, do NOT extract" stance, plus a first-person
present-want gate. The node only EXTRACTS candidates into state['intentions'];
resolution against existing intentions + persistence happen in store_node (P2).

PRECISION is the gate (>=0.90 mean, N>=3) — see evals/intention_extraction_eval.py.
This node is prompt-only by design; a deterministic backstop
(drop_non_intentions) is added ONLY if the prompt alone can't clear the gate,
mirroring how deadline.py earned drop_past_event_deadlines.
"""
from app.llm import flash as model
from app.schemas.pipeline import IntentionList
from app.state import JournalState

# Gemini enforces the IntentionList shape (list-wrapped object). Normalization
# and per-entry dedup stay as Python post-processing below.
structured_model = model.with_structured_output(IntentionList, method="json_schema")


def normalize_intention_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def dedup_intentions(items: list[dict]) -> list[dict]:
    """Collapse same-entry restatements by normalized text. Cross-entry
    resolution (re-reference vs new goal) is a separate, semantic step in P2."""
    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        key = item["text"]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def build_intention_prompt(text: str, raw_text: str) -> str:
    return f"""
You are a strict STATED-INTENTION extraction engine.

A STATED INTENTION is an UNDATED aspiration the writer expresses a PRESENT, FIRST-PERSON want or intent to do — something they WANT to start, resume, or do more of, but are NOT YET doing. Most journal text is NOT an intention. When unsure, do NOT extract.

EXTRACT an item ONLY when ALL of these hold:
- FIRST PERSON: it is the WRITER'S OWN want/intent, not someone else's.
- PRESENT WANT/INTENT: a current desire or resolve — "I want to", "I keep meaning to", "I've been wanting to", "I'd love to", "I keep telling myself I'll", "I really want to". A frustrated LAMENT that clearly contains such a desire DOES count: "I hate that I never make it to the gym" -> "get back to the gym".
- NOT YET DOING IT: the thing has not started, or it lapsed and they want to return to it.

DO NOT EXTRACT (these are the traps):
- PAST narration of what already happened: "went to the gym", "called mom yesterday", "wrote three pages today", "cooked dinner on Sunday". Completed actions are NEVER intentions.
- ALREADY ACTING — something the writer has already STARTED or is currently doing: "started Spanish lessons this week", "been hitting the gym daily", "picked the guitar back up", "three weeks into running". Current behaviour is not a future intention.
- DATED OBLIGATIONS / tasks tied to a date or deadline: "submit the form by Friday", "dentist appointment Tuesday", "pay rent on the 1st", "meeting tomorrow". Those are deadlines, handled elsewhere — NOT intentions.
- A BARE, GENERIC 'should' with no concrete want: "I should eat better", "I should sleep more", "should get my act together". Vague self-improvement venting is NOT a stated intention.
- SOMEONE ELSE'S want: "my friend wants to learn Spanish", "my sister says she'll start running".
- NONCOMMITTAL musing or a question: "maybe I'll travel more, who knows", "should I take up a new hobby?".
- Pure observation, mood, gratitude, or reflection with no want to act.

Cleaned Input:
{text}

Raw Input:
{raw_text}

Output Rules:
- FINAL CHECK before returning: for each item, confirm it is a PRESENT, FIRST-PERSON want to do something NOT YET being done. If it describes something already done or already underway, or it is a dated task, or it is a bare 'should', REMOVE it.
- "text" = a SHORT, clean, canonical phrase for the aspiration in the writer's voice: lowercase verb phrase, NO date, NO surrounding narration. Examples: "get back to the gym", "learn spanish", "call mom more", "start writing again", "save money".
- If the same intention is stated more than once, return it only ONCE.
- Return all intentions under an "intentions" key. If none exist, return {{"intentions": []}}.
- Use exactly the key "text" for each item. Do not include dates or any other field.

Format:
{{"intentions": [
  {{"text": "get back to the gym"}},
  {{"text": "learn spanish"}}
]}}
""".strip()


async def extract_intentions(state: JournalState) -> dict:
    text = state["cleaned_text"]
    raw_text = state["raw_text"]

    prompt = build_intention_prompt(text, raw_text)
    result = await structured_model.ainvoke(prompt)

    items = [
        {"text": normalize_intention_text(intention.text)}
        for intention in result.intentions
        if (intention.text or "").strip()
    ]
    items = dedup_intentions(items)

    return {"intentions": items}
