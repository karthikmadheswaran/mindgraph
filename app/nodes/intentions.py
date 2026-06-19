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
import logging
import re

from app.llm import flash as model
from app.schemas.pipeline import IntentionList
from app.state import JournalState

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Deterministic precision backstop (the "reliable" half behind the soft prompt).
# Prompt-only flash-lite over-extracts — measured precision 0.63, recall 1.0
# (evals/intention_extraction_eval.py). This guard DROPS a candidate whose source
# phrase shows a disqualifying signal (third-person subject, a date/deadline,
# completed/already-acting past tense, a noncommittal hedge, or a bare 'should')
# UNLESS the phrase also carries a clear first-person present-want / resumption /
# lament cue that rescues it ("I still haven't started learning to drive" keeps
# the 'started' past-tense via the lament cue — the deadline guard's
# open-obligation-override pattern).
#
# Scope (same honest bound as deadline.drop_past_event_deadlines): keyed on
# ENGLISH morphology + cue phrases. Unlike the deadline guard it FAILS TOWARD
# DROPPING — precision is the gate; recall is secondary and self-healing (a real
# intention recurs in a later entry and is caught then). Do NOT pile on more
# language rules; the model-based path is the upgrade if non-English / unusual
# phrasings push recall too low.
# ---------------------------------------------------------------------------

# First-person present want / resumption / lament — these RESCUE a candidate even
# when a disqualifier is also present. First-person-anchored on purpose: "i want
# to" rescues, but third-person "people want to" / "my friend wants to" must NOT.
_WANT_CUES = (
    "i want", "i really want", "i just want", "i do want", "really want to",
    "do want to", "i'd love", "i would love", "i've been wanting", "been wanting to",
    "i keep meaning", "keep meaning to", "i keep telling myself", "keep telling myself",
    "i keep saying", "keep saying i", "i'll finally", "i keep thinking i",
    "i'd like", "i think i want", "gotta start", "gotta ",
)
_RESUMPTION_CUES = ("get back to", "get back in", "back into", " again")
_LAMENT_CUES = (
    "hate that", "still haven't", "still havent", "haven't started", "havent started",
    "never make it", "frustrates me that i",
)

# Disqualifiers — the systematic false-positive categories measured in the eval.
_THIRD_PERSON = (
    "my friend", "my sister", "my brother", "my mom", "my mum", "my dad",
    "my partner", "she wants", "he wants", "they want", "everyone",
    "people want", "a lot of people", "lot of people",
)
_HEDGE = ("maybe", "who knows", "not sure", "should i ", "?")
_PAST_ACTING = (
    "submitted", "renewed", "started", "wrote", "finished", "picked", "cooked",
    "called", "went", "practiced", "missed", "been hitting", "been journaling",
    "weeks into", "for two weeks", "this week", "got going", "made real progress",
    # past-state echoes (the model sometimes returns a whole observation sentence
    # as an "intention"). Rescue-protected: the 2 positives with "was" carry an
    # "i want"/"get back to" cue, so they survive.
    "was ", "were ", "has been", "have been",
)
_DATE_MARKERS = (
    "tomorrow", "next week", "next month", "next tuesday", "by monday", "by tuesday",
    "by wednesday", "by thursday", "by friday", "by saturday", "by sunday",
    "appointment", "deadline",
)
_ORDINAL_DATE_RE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)\b")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _is_rescued(probe: str) -> bool:
    return any(c in probe for c in _WANT_CUES + _RESUMPTION_CUES + _LAMENT_CUES)


def _is_disqualified(probe: str) -> bool:
    if any(m in probe for m in _THIRD_PERSON + _HEDGE + _PAST_ACTING + _DATE_MARKERS):
        return True
    if _ORDINAL_DATE_RE.search(probe) or _ISO_DATE_RE.search(probe):
        return True
    return "should" in probe  # bare 'should' venting, unless rescued above


# A canonical intention is a SHORT verb phrase. A long `text` means the model
# echoed a sentence instead of canonicalizing — drop it (also keeps drift cards
# readable). Real fixtures top out well under this.
_MAX_INTENTION_TEXT_LEN = 80

# Inverted-urge guard: the writer journals about RESISTING/QUITTING a habit, so
# the urge itself ("smoke", "take a break and smoke") must NEVER become a drift
# card — surfacing it would nag them toward the thing they're trying to stop, and
# their actual GOAL is the opposite. KEEP the quit-framed goal ("not be a
# smoker", "quit smoking", "skip the cigarette"). Scoped to smoking-class urges
# (the only one in real data); extend only if real traffic shows another.
_URGE_TOKENS = ("smoke", "smoking", "cigarette", "cigarettes", "vape", "vaping", "nicotine")
_QUIT_MARKERS = (
    "not ", "quit", "stop", "skip", "give up", "gave up", "cut down", "cut back",
    "less", "no more", "avoid", "resist", "without", "instead",
)

# Contentless guard: a real intention names a concrete object/aim. Pronoun-only /
# filler fragments ("go back", "fix it though", "sort that one too", "see how it
# goes", "hope for it a lot") carry no action object. A candidate is contentless
# when EVERY token is a function/vague word — the concrete nouns in real
# intentions (gym, job, keyboard, AND dev-task objects like "rag system") always
# leave at least one content token, so dev-TODOs are NOT dropped.
_NONCONTENT = {
    "a", "an", "the", "to", "of", "in", "on", "for", "and", "or", "but", "with", "at", "by",
    "as", "from", "my", "me", "i", "we", "us", "our", "you", "your", "myself", "it", "its",
    "that", "this", "these", "those", "them", "they", "is", "am", "are", "was", "were", "be",
    "been", "being", "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "should", "may", "might", "must", "not", "no", "just", "really", "very", "so", "too",
    "though", "also", "again", "back", "now", "then", "here", "there", "up", "down", "out",
    "about", "around", "over", "like", "how", "if", "well", "more", "less", "much", "many",
    "some", "any", "all", "quite", "still", "yet", "maybe", "somehow", "go", "going", "goes",
    "gone", "went", "see", "seeing", "seen", "hope", "hoping", "sort", "sorting", "work",
    "working", "works", "fix", "fixing", "check", "checking", "keep", "keeping", "try", "trying",
    "get", "getting", "make", "making", "want", "wanting", "need", "needing", "thing", "things",
    "stuff", "one", "ones", "something", "anything", "everything", "nothing", "way", "ways",
    "lot", "lots", "bit", "kind",
}


def _is_inverted_urge(probe: str) -> bool:
    if not any(t in probe for t in _URGE_TOKENS):
        return False
    return not any(q in probe for q in _QUIT_MARKERS)  # keep the quit-framed goal


def _is_contentless(text: str) -> bool:
    tokens = [t.strip("'\".,!?;:()-") for t in text.lower().split()]
    tokens = [t for t in tokens if t]
    return bool(tokens) and all(t in _NONCONTENT for t in tokens)


def drop_non_intentions(items: list[dict]) -> list[dict]:
    """Drop candidates that are over-long, inverted urges, contentless, or
    disqualified-and-not-rescued. Precision backstop."""
    kept: list[dict] = []
    for item in items:
        text = item.get("text", "")
        if len(text) > _MAX_INTENTION_TEXT_LEN:
            continue
        probe = f"{item.get('raw_text', '')} {text}".lower()
        if _is_inverted_urge(probe):       # "smoke" when journaling about quitting
            continue
        if _is_contentless(text):          # "go back", "fix it though"
            continue
        if _is_disqualified(probe) and not _is_rescued(probe):
            continue
        kept.append(item)
    return kept


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

Do NOT extract examples like:
- "the sky looked amazing on my walk today" / "work has been chaotic all week" -> pure observation, NOT an intention.
- "I felt drained and a bit sad tonight" -> mood / reflection, NOT an intention.
- "reading more is good for you" / "it'd be great if people exercised more" -> abstract or general statements, NOT the writer's own intention.
- "my brother wants to get into photography" -> someone else's want, NOT yours.
- "I have to renew my licence by next month" -> a dated obligation (a deadline), NOT an intention.
- "I finally cancelled that subscription" -> a completed action, NOT an intention.
- "I've been going to the gym every day lately" -> already happening, NOT a future intention.
- NEVER return a whole narrated sentence as "text"; if there is no genuine first-person want, return nothing.

Cleaned Input:
{text}

Raw Input:
{raw_text}

Output Rules:
- FINAL CHECK before returning: for each item, confirm it is a PRESENT, FIRST-PERSON want to do something NOT YET being done. If it describes something already done or already underway, or it is a dated task, or it is a bare 'should', REMOVE it.
- "text" = a SHORT, clean, canonical phrase for the aspiration in the writer's voice: lowercase verb phrase, NO date, NO surrounding narration. Examples: "get back to the gym", "learn spanish", "call mom more", "start writing again", "save money".
- "raw_text" = the EXACT phrase or sentence from the entry that states this intention, copied verbatim from the input (used to verify it).
- If the same intention is stated more than once, return it only ONCE.
- Return all intentions under an "intentions" key. If none exist, return {{"intentions": []}}.
- Use exactly the keys "text" and "raw_text" for each item. Do not include dates or any other field.

Format:
{{"intentions": [
  {{"text": "get back to the gym", "raw_text": "I want to get back to the gym"}},
  {{"text": "learn spanish", "raw_text": "I keep meaning to learn Spanish"}}
]}}
""".strip()


async def extract_intentions(state: JournalState) -> dict:
    text = state["cleaned_text"]
    raw_text = state["raw_text"]

    prompt = build_intention_prompt(text, raw_text)
    try:
        result = await structured_model.ainvoke(prompt)
    except Exception as exc:
        # Rate/quota errors must PROPAGATE — live treats them as a retryable entry
        # error, and the backfill retries them with backoff (else a transient 429
        # would silently drop real intentions). Any OTHER error (e.g. a parse the
        # schema can't bind) fails safe — extract nothing rather than crash the
        # fan-out node and error the whole entry.
        msg = str(exc).lower()
        if any(s in msg for s in ("429", "resource exhausted", "exhausted", "quota")):
            raise
        logger.warning("extract_intentions: structured parse failed; extracting nothing: %s", exc)
        return {"intentions": []}

    # Structured decoding returns None on an empty/blocked/zero-token response
    # (observed under Vertex 429 pressure; the same flash-lite pathology noted
    # for the routing node). Fail safe — extract nothing rather than crash the
    # fan-out node and error the whole entry.
    if result is None:
        logger.warning("extract_intentions: structured output was None; extracting nothing")
        return {"intentions": []}

    items = [
        {
            "text": normalize_intention_text(intention.text),
            "raw_text": (intention.raw_text or "").strip(),
        }
        for intention in result.intentions
        if (intention.text or "").strip()
    ]
    items = dedup_intentions(items)
    items = drop_non_intentions(items)  # deterministic precision backstop

    return {"intentions": items}
