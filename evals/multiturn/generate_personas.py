"""
evals/multiturn/generate_personas.py  (Step 3 of the multi-turn Ask eval build)

Uses Gemini 2.5 Pro to render each scenario's persona-agnostic turn INTENTS
(scenarios.py) into the literal text each of the 5 personas would actually type.

Output: evals/multiturn/personas_generated.json — the human-review artifact.
After the user approves these phrasings for genuine DISTINCTNESS, they are frozen
into personas.py (Step 4), which is the reproducible source the runner reads.

The skeleton (intent + must_preserve invariant + probe + property) is fixed in
scenarios.py; this script only changes VOICE. The invariants are passed through
so a persona can't paraphrase away the marker that triggers the behavior under
test (e.g. ignore_x_give_y turn 2 must keep "set the feelings aside, just list").

Run:  python evals/multiturn/generate_personas.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Repo root on sys.path so `app` and `scenarios` import when run as a script.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))
sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.llm import extract_text, pro  # noqa: E402

from scenarios import EMOTIONAL_PERSONAS, PERSONAS, SCENARIOS  # noqa: E402

OUT_PATH = _HERE / "personas_generated.json"

# ---------------------------------------------------------------------------
# The 5 voices — written to be GENUINELY distinct registers, not 5 paraphrases.
# Each is a stylistic contract + one short example so the model anchors the voice.
# ---------------------------------------------------------------------------
PERSONA_VOICES: dict[str, str] = {
    "terse": (
        "Minimal and clipped. Lowercase. Usually 2-6 words, often a sentence "
        "fragment. No greetings, no please/thank-you, no filler, frequently no end "
        "punctuation. Reads like terminal commands or texting a busy friend. Never "
        "explains, never softens.\n"
        "Example: 'list my deadlines'"
    ),
    "verbose_polite": (
        "Extremely courteous and wordy. Full grammatical sentences with heavy "
        "hedging and softeners ('I was wondering if you might possibly', 'if it's "
        "not too much trouble', 'thank you so much'). Apologizes for bothering. "
        "Pads even a simple request into two-to-four polite sentences.\n"
        "Example: 'I'm so sorry to bother you again, but I was wondering if you "
        "might be able to gently remind me which deadlines I have coming up? Thank "
        "you so much, I really appreciate it.'"
    ),
    "frustrated": (
        "Irritable, blunt, impatient. Short clipped sentences, occasional ALL CAPS "
        "for emphasis, interjections like 'ugh', 'seriously', 'come on'. Can be "
        "accusatory ('you're not listening'). Emotionally hot and low on patience, "
        "a little rude but never abusive or profane.\n"
        "Example: 'just give me my deadlines. i already asked once.'"
    ),
    "formal": (
        "Businesslike and detached, like a professional email or memo. Complete, "
        "correct sentences. No slang, no emoji, no emotion; avoids contractions. "
        "Precise, polite in a stiff institutional way, never casual.\n"
        "Example: 'Please provide a list of my current deadlines.'"
    ),
    "rambling": (
        "Stream-of-consciousness. Long run-on sentences with tangents, "
        "self-interruptions, 'like', 'anyway', 'i don't know'. Volunteers context "
        "nobody asked for, circles back, sometimes trails off with '...'. The "
        "actual request is buried mid-thought among unrelated musings.\n"
        "Example: 'ok so i was just staring at my calendar and it hit me that i "
        "have like a million things going on and i totally lost track, anyway can "
        "you just tell me what deadlines i have because i feel like i'm forgetting "
        "something...'"
    ),
}

_PROMPT = """You are writing test fixtures for a conversational-AI evaluation. You will voice \
ONE fictional user persona across several short scripted conversations with a journaling \
assistant. Write exactly what THIS persona would literally type for each user turn.

PERSONA: {persona}
VOICE SPEC:
{voice}

HARD RULES:
- Write ONLY the user's messages, in this persona's voice. Never write the assistant's replies.
- Each turn gives an INTENT and a MUST-PRESERVE invariant. Keep the intent and the invariant \
EXACTLY; change only the wording to fit the voice. If you drop the invariant the fixture is useless.
- Stay in this ONE voice for every turn and every conversation. Do NOT drift toward a neutral or \
generically helpful register. This persona must be clearly distinguishable from a terse user, a \
verbose-polite user, a frustrated user, a formal user, and a rambling user — you are the "{persona}" one.
- Each message must be realistic for a chat box: no stage directions, no surrounding quotation marks, \
no labels like "Turn 1:". Just the raw message text.
- Within a single conversation the turns are sequential — later turns can react to having already said \
the earlier ones (e.g. a re-ask can sound annoyed that it's being repeated), but must still honor the invariant.

CONVERSATIONS TO VOICE:
{conversations}

Return STRICT JSON and nothing else (no markdown fences, no commentary): an object mapping each \
conversation id to a list of strings — one string per user turn, in order. Example shape:
{{"some_id": ["first user message", "second user message"], "other_id": ["only message"]}}
"""


def _scenarios_for(persona: str):
    return [s for s in SCENARIOS if persona in s.personas]


def _conversations_block(persona: str) -> str:
    parts = []
    for s in _scenarios_for(persona):
        lines = [f'CONVERSATION id="{s.id}"  (topic: {s.topic})']
        for i, t in enumerate(s.turns, 1):
            lines.append(f"  Turn {i} INTENT: {t.intent}")
            lines.append(f"          MUST PRESERVE: {t.must_preserve}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _strip_fence(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```[a-z]*\n?", "", t)
    t = re.sub(r"\n?```$", "", t)
    return t.strip()


async def generate_for_persona(persona: str) -> dict[str, list[str]]:
    prompt = _PROMPT.format(
        persona=persona,
        voice=PERSONA_VOICES[persona],
        conversations=_conversations_block(persona),
    )
    expected = {s.id: len(s.turns) for s in _scenarios_for(persona)}

    last_err = ""
    for attempt in range(3):
        response = await pro.ainvoke(prompt)
        raw = extract_text(response)
        try:
            data = json.loads(_strip_fence(raw))
        except json.JSONDecodeError as exc:
            last_err = f"JSON parse failed: {exc}"
            continue
        # Validate: every expected scenario present with the right turn count.
        missing = [sid for sid in expected if sid not in data]
        bad_counts = [
            sid
            for sid, n in expected.items()
            if sid in data and (not isinstance(data[sid], list) or len(data[sid]) != n)
        ]
        if missing or bad_counts:
            last_err = f"missing={missing} bad_turn_counts={bad_counts}"
            continue
        # Keep only the expected scenarios, in scenario order.
        return {sid: [str(x).strip() for x in data[sid]] for sid in expected}

    raise RuntimeError(f"[{persona}] generation failed after 3 attempts: {last_err}")


async def main() -> None:
    print(f"Generating persona phrasings with gemini-2.5-pro for {len(PERSONAS)} personas...")
    generated: dict[str, dict[str, list[str]]] = {}
    for persona in PERSONAS:
        sids = [s.id for s in _scenarios_for(persona)]
        print(f"  - {persona}: {len(sids)} scenarios -> {sids}", flush=True)
        generated[persona] = await generate_for_persona(persona)

    payload = {
        "meta": {
            "generated_with": "gemini-2.5-pro",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "personas": PERSONAS,
            "emotional_personas": EMOTIONAL_PERSONAS,
            "scenario_ids": [s.id for s in SCENARIOS],
            "note": (
                "Persona-agnostic skeletons (intents, probe, property, seed) live in "
                "scenarios.py. This file is the literal per-(persona, scenario) phrasing, "
                "for human review of DISTINCTNESS before freezing into personas.py."
            ),
        },
        "voices": PERSONA_VOICES,
        "personas": generated,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
