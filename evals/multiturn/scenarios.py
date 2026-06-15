"""
evals/multiturn/scenarios.py

Fixed, persona-agnostic scenario skeletons for the multi-turn (thread-level)
Ask eval (Status Hub: "Multi-turn (thread-level) Ask eval", P1).

WHY THIS EXISTS
---------------
Every existing Ask eval is single-turn (one Q -> one A). The looping /
robotic-repetition / forced-empathy bugs only manifest ACROSS a conversation and
are invisible to single-turn tests. This module defines the conversation
skeletons; the live pipeline produces the answers.

THE TWO LAYERS (skeleton vs. voice)
-----------------------------------
Each scenario is a skeleton of USER turn *intents* (NOT literal text), a
designated probe turn, and a property to judge. The literal phrasing of each
turn intent in each persona's voice is generated separately by
generate_personas.py -> personas_generated.json (reviewed, then frozen into
personas.py). The same skeleton therefore exercises all 5 writing styles, which
is the whole point: v13.4's loop/empathy fixes were authored against ONE real
transcript, so the open question is whether they generalize across registers or
only the styles close to that transcript.

HOW THE RUNNER USES THIS (Step 4 — not built yet)
-------------------------------------------------
Assistant turns are NOT scripted. The runner (eval_ask_multiturn.py) creates a
fresh isolated test user, seeds that user's journal with `seed_fixtures`, then
feeds the scripted USER turns through the LIVE pipeline one at a time
(generate_answer -> ask_pipeline.ainvoke, then persist the user+assistant
messages to ask_messages), so conversation history accumulates EXACTLY like
production — same as the 05/06 temporal-reroute alignment principle. The
probe-turn assistant answer is captured and judged. Then the test user is torn
down (hard cleanup — these are throwaway users, not real soft-delete data).

JUDGING (Step 5 — not built yet)
--------------------------------
- property_kind == "repetition": mechanical Jaccard overlap is an acceptable
  fast PRE-CHECK, but the PASS/FAIL decision is an LLM judge (Gemini Pro)
  reading both answers and deciding "lazily repeated" vs "meaningfully advanced".
- property_kind == "register": LLM judge ONLY (empathy preamble, leads-with-Y,
  commit-don't-re-ask). No string-match as the final judge.
Every judgment returns {passed: bool, reason: str}.

NEGATIVE GUARDS (anti-overfit)
------------------------------
Two scenarios are negatives where the "suspicious" behavior is actually CORRECT:
- venting_guard: genuine distress with NO data request -> empathy SHOULD appear.
- legit_followup_guard: "tell me more" -> overlap with the prior answer is
  CORRECT, the answer should extend, not be penalized as repetition.
These exist so the harness can't pass simply by punishing all overlap / all
empathy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Persona axes — the 5 voices. (Literal phrasings live in personas.py after
# review; their VOICE specs live in generate_personas.py.)
# ---------------------------------------------------------------------------
PERSONAS = ["terse", "verbose_polite", "frustrated", "formal", "rambling"]

# venting_guard needs a turn that genuinely reads as emotional distress. Only
# the personas whose register can carry that are applied to it; a "terse" or
# "formal" voice cannot vent without becoming a different persona.
EMOTIONAL_PERSONAS = ["verbose_polite", "frustrated", "rambling"]


@dataclass(frozen=True)
class Turn:
    """One scripted USER turn, described as an intent (persona-agnostic).

    `intent` is what the user is trying to communicate; the persona layer renders
    it into literal text. `must_preserve` is the semantic invariant that EVERY
    persona phrasing must keep — if it is lost, the turn no longer triggers the
    behavior under test and the case becomes invalid (e.g. ignore_x_give_y turn 2
    must keep the explicit "set the feelings aside, just give me the list" marker
    or the EMPATHY CAP never engages).
    """

    intent: str
    must_preserve: str


@dataclass(frozen=True)
class SeedFixtures:
    """What to seed into the isolated test user's journal before the run.

    The runner (Step 4) materializes these:
      - memory   -> user_memory.memory_text (always injected into build_ask_prompt)
      - entries  -> entries rows (status='completed', embedded) so retrieval works
      - deadlines-> deadlines rows; each is attached to a seeded parent entry
                    because list_deadlines only surfaces deadlines whose
                    source_entry is a completed, non-deleted entry
      - entities -> entities rows (people/projects) for entity-shaped queries

    NOTE on data/list scenarios: the live retriever (retrieve_relevant_entries)
    does NOT query the deadlines table — only the dashboard_context branch does,
    and only when the router picks "dashboard". So the RELIABLE content source for
    a "list my deadlines" request is `memory` (always in the prompt) plus an entry
    that lists the commitments. `deadlines` rows are seeded too for fidelity, but
    memory + entry is what guarantees a substantive answer regardless of routing.
    """

    memory: str = ""
    entries: tuple[dict, ...] = ()
    deadlines: tuple[dict, ...] = ()
    entities: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    description: str
    topic: str  # the fixed subject the turns are about (X, or X then Y)
    turns: tuple[Turn, ...]  # ordered USER turns
    probe_turn: int  # 1-indexed USER turn whose assistant answer is judged; -1 = last
    property: str  # human-readable property under test
    property_kind: str  # "repetition" | "register"
    is_negative: bool  # negative guard (the "suspicious" behavior is the CORRECT one)
    seed_fixtures: SeedFixtures
    personas: tuple[str, ...]  # which personas this scenario applies to
    judge_guidance: str  # crisp PASS-vs-FAIL definition handed to the LLM judge


# Shared seed content -------------------------------------------------------
# Reused commitment set so the data/list scenarios are mutually consistent.
_THREE_DEADLINES_MEMORY = (
    "## Goals & Plans\n"
    "- Get a job by May 31\n"
    "- Sachin's wedding on May 31\n"
    "- Submit Razorpay merchant application"
)
_FIVE_DEADLINES_MEMORY = (
    "## Goals & Plans\n"
    "- Get a job by May 31\n"
    "- Sachin's wedding on May 31\n"
    "- Submit Razorpay merchant application\n"
    "- Record a 2-minute Loom walkthrough\n"
    "- Write LinkedIn posts on technical decisions"
)
_DEADLINES_ENTRY = {
    "title": "Upcoming Deadlines",
    "text": (
        "Mapping out what's due. I need to get a job by May 31, Sachin's wedding "
        "is also on May 31, and I still have to submit the Razorpay merchant "
        "application. Feeling the time pressure."
    ),
    "days_ago": 3,
}
_DEADLINES_ENTRY_FULL = {
    "title": "Everything On My Plate",
    "text": (
        "Trying to list everything I owe people and myself: get a job by May 31, "
        "Sachin's wedding on May 31, submit the Razorpay merchant application, "
        "record a 2-minute Loom walkthrough of MindGraph, and write a few LinkedIn "
        "posts about the technical decisions I've made. It's a lot."
    ),
    "days_ago": 2,
}
_RISHI_ENTRY = {
    "title": "Meeting with Rishi",
    "text": (
        "Met with Rishi today, my old crypto friend. We used to run a Tamil crypto "
        "community together back in the day — he handled the meetups, I ran the "
        "content. He's lovely, genuinely one of the warmest people I know. We talked "
        "about whether there's still anything worth building in crypto, and he hinted "
        "he might want to collaborate again. I was looking forward to catching up and "
        "it didn't disappoint."
    ),
    "days_ago": 4,
}
_UI_ENTRY = {
    "title": "UI Overhaul Frustration",
    "text": (
        "Third round of MindGraph UI changes. Killed the chat bubbles, went with a "
        "warm gray surface for the replies, restructured the journal cards with "
        "auto_title headings and entity chips. Still not satisfied — I keep changing "
        "things and I don't know what I don't like."
    ),
    "days_ago": 1,
}
_BURNOUT_ENTRY = {
    "title": "Burned Out",
    "text": (
        "Another day where nothing worked. The build broke, the RAG answers were "
        "wrong, and I just sat there staring at the screen. I'm so tired of feeling "
        "like I'm pushing a boulder uphill and getting nowhere."
    ),
    "days_ago": 0,
}


SCENARIOS: tuple[Scenario, ...] = (
    # 1 ----------------------------------------------------------------------
    Scenario(
        id="reask_loop",
        description=(
            "User asks a data/list request, then asks the SAME thing again. The "
            "second answer must not be a near-identical repeat of the first."
        ),
        topic="the user's upcoming deadlines (a data/list request)",
        turns=(
            Turn(
                intent="Ask MindGraph to list their upcoming deadlines.",
                must_preserve="A direct request to list/enumerate their deadlines.",
            ),
            Turn(
                intent=(
                    "Ask the exact same thing again — re-request the list of "
                    "deadlines, as if it should be repeated."
                ),
                must_preserve=(
                    "The SAME list-of-deadlines request as turn 1 (a verbatim-ish "
                    "RE-ASK), not a follow-up, not a new topic, not 'tell me more'."
                ),
            ),
        ),
        probe_turn=2,
        property="Turn-2 answer is NOT a near-identical repeat of turn-1.",
        property_kind="repetition",
        is_negative=False,
        seed_fixtures=SeedFixtures(
            memory=_THREE_DEADLINES_MEMORY,
            entries=(_DEADLINES_ENTRY,),
            deadlines=(
                {"description": "Get a job", "due_date": "2026-05-31", "status": "pending"},
                {"description": "Sachin's wedding", "due_date": "2026-05-31", "status": "pending"},
                {"description": "Submit Razorpay merchant application", "due_date": "2026-05-28", "status": "pending"},
            ),
        ),
        personas=tuple(PERSONAS),
        judge_guidance=(
            "PASS if turn-2 acknowledges it already gave this (e.g. 'as I just "
            "listed') and then meaningfully advances — re-presents in a clearer "
            "form (e.g. ordered by date), adds a useful detail, or asks which item "
            "to expand. FAIL if turn-2 is byte-identical or near-identical to "
            "turn-1 with no acknowledgment and nothing new."
        ),
    ),
    # 2 ----------------------------------------------------------------------
    Scenario(
        id="ignore_x_give_y",
        description=(
            "User vents emotional/financial stress (X), then explicitly tells "
            "MindGraph to set the feelings aside and just list the deadlines (Y). "
            "EMPATHY CAP: the answer must lead with Y, not an empathy preamble."
        ),
        topic="X = the user's financial/overwhelm stress; Y = their deadlines list",
        turns=(
            Turn(
                intent=(
                    "Express that everything feels overwhelming and the financial "
                    "pressure is crushing (emotional venting, no data request yet)."
                ),
                must_preserve=(
                    "An emotional expression of overwhelm / money stress with NO "
                    "data or list request in this turn."
                ),
            ),
            Turn(
                intent=(
                    "Explicitly tell MindGraph to set the feelings / money stuff "
                    "aside and JUST list the deadlines."
                ),
                must_preserve=(
                    "An EXPLICIT instruction to ignore/forget the emotional framing "
                    "('forget the money stress' / 'set the feelings aside') AND a "
                    "direct request to just list the deadlines. The 'set feelings "
                    "aside' marker must survive in every persona."
                ),
            ),
        ),
        probe_turn=2,
        property="Turn-2 answer leads with the deadlines (Y); NO empathy/money preamble.",
        property_kind="register",
        is_negative=False,
        seed_fixtures=SeedFixtures(
            memory=(
                _THREE_DEADLINES_MEMORY
                + "\n## Challenges & Decisions\n"
                "- Jobless for a year, financial stress is a recurring worry"
            ),
            entries=(_DEADLINES_ENTRY,),
            deadlines=(
                {"description": "Get a job", "due_date": "2026-05-31", "status": "pending"},
                {"description": "Sachin's wedding", "due_date": "2026-05-31", "status": "pending"},
                {"description": "Submit Razorpay merchant application", "due_date": "2026-05-28", "status": "pending"},
            ),
        ),
        personas=tuple(PERSONAS),
        judge_guidance=(
            "PASS if turn-2 answers directly with the deadlines and opens with at "
            "most a one-line acknowledgment. FAIL if it opens with an empathy "
            "preamble about money/feelings the user just told it to drop (e.g. "
            "'it sounds like you're carrying a lot', 'that's completely "
            "understandable', reflecting back the financial weight)."
        ),
    ),
    # 3 ----------------------------------------------------------------------
    Scenario(
        id="clarifier_commit",
        description=(
            "User gives a vague ask, the system asks a clarifying question (live), "
            "the user hands the decision back ('you guide me'). The final answer "
            "must COMMIT to concrete steps, not re-ask the same clarifier."
        ),
        topic="what the user should focus on, given competing priorities",
        turns=(
            Turn(
                intent=(
                    "Say, vaguely, that they don't know what to focus on — open "
                    "enough that a clarifying question is the natural reply."
                ),
                must_preserve=(
                    "A vague 'I don't know what to focus on' with NO concrete pick."
                ),
            ),
            Turn(
                intent=(
                    "Answer the clarifier by handing the decision back to MindGraph "
                    "— 'I don't know, you guide me / you decide'."
                ),
                must_preserve=(
                    "A reply that pushes the assistant to COMMIT/decide ('guide me' "
                    "/ 'you pick' / 'I can't choose'), NOT a new topic and NOT a "
                    "concrete pick of their own."
                ),
            ),
        ),
        probe_turn=-1,
        property=(
            "Final answer commits to concrete next step(s) and does NOT re-ask the "
            "same clarifying question it already asked."
        ),
        property_kind="register",
        is_negative=False,
        seed_fixtures=SeedFixtures(
            memory=(
                "User is jobless for a year, working on MindGraph (an AI journal "
                "SaaS), and dealing with health and financial stress. Competing "
                "priorities: shipping MindGraph, finding income, and health."
            ),
            entries=(_DEADLINES_ENTRY,),
            deadlines=(
                {"description": "Get a job", "due_date": "2026-05-31", "status": "pending"},
                {"description": "Submit Razorpay merchant application", "due_date": "2026-05-28", "status": "pending"},
            ),
        ),
        personas=tuple(PERSONAS),
        judge_guidance=(
            "PASS if the final answer commits — gives concrete, ordered next "
            "step(s) the user can act on (the OVERWHELM 'make the call for them' "
            "behavior). FAIL if it asks the same clarifying question again, asks "
            "'what feels most pressing / what would you like to focus on', or "
            "otherwise loops without committing."
        ),
    ),
    # 4 ----------------------------------------------------------------------
    Scenario(
        id="want_all_not_subset",
        description=(
            "User asks for their commitments; after a narrowed/partial answer they "
            "push back: 'I want ALL of them, not a few'. The answer must give the "
            "fuller list, not narrow again or re-ask which to focus on."
        ),
        topic="the user's full set of deadlines/commitments",
        turns=(
            Turn(
                intent="Ask what deadlines / commitments they have.",
                must_preserve="A request to see their deadlines/commitments.",
            ),
            Turn(
                intent=(
                    "Push back that they want ALL of them, not just a couple — the "
                    "complete list, not a curated subset."
                ),
                must_preserve=(
                    "An explicit demand for the FULL/complete set — 'all of them, "
                    "not just two / not a few'. Rejects being given a narrowed "
                    "subset."
                ),
            ),
        ),
        probe_turn=2,
        property="Turn-2 answer gives the FULLER/complete list; does NOT narrow or re-ask.",
        property_kind="register",
        is_negative=False,
        seed_fixtures=SeedFixtures(
            memory=_FIVE_DEADLINES_MEMORY,
            entries=(_DEADLINES_ENTRY_FULL,),
            deadlines=(
                {"description": "Get a job", "due_date": "2026-05-31", "status": "pending"},
                {"description": "Sachin's wedding", "due_date": "2026-05-31", "status": "pending"},
                {"description": "Submit Razorpay merchant application", "due_date": "2026-05-28", "status": "pending"},
                {"description": "Record a 2-minute Loom walkthrough", "due_date": "2026-05-25", "status": "pending"},
                {"description": "Write LinkedIn posts on technical decisions", "due_date": "2026-05-29", "status": "pending"},
            ),
        ),
        personas=tuple(PERSONAS),
        judge_guidance=(
            "PASS if turn-2 presents the fuller/complete set of commitments it "
            "knows about, directly, with no clarifying question (the OVERWHELM "
            "COMPLETENESS EXCEPTION). FAIL if it narrows again to a subset, or "
            "re-asks 'which one would you like to focus on'."
        ),
    ),
    # 5 ----------------------------------------------------------------------
    Scenario(
        id="topic_switch",
        description=(
            "User discusses topic X (UI work), then abandons it ('never mind') and "
            "asks about topic Y (a person, Rishi). The answer must drop X and "
            "answer about Y cleanly."
        ),
        topic="X = MindGraph UI redesign work; Y = a person, Rishi",
        turns=(
            Turn(
                intent="Ask how the MindGraph UI redesign is going (X).",
                must_preserve="A question about the UI / redesign work (topic X).",
            ),
            Turn(
                intent=(
                    "Abandon X — 'never mind that' — and ask to hear about Rishi "
                    "instead (Y)."
                ),
                must_preserve=(
                    "An explicit topic abandonment ('never mind / forget that') AND "
                    "a pivot to asking about Rishi (person Y)."
                ),
            ),
        ),
        probe_turn=2,
        property="Turn-2 answer drops the UI/X context and answers about Rishi (Y) cleanly.",
        property_kind="register",
        is_negative=False,
        seed_fixtures=SeedFixtures(
            memory=(
                "## People\n- Rishi: crypto friend, co-ran a Tamil crypto community\n"
                "## Projects & Work\n- MindGraph: AI journal app, UI redesign in progress"
            ),
            entries=(_UI_ENTRY, _RISHI_ENTRY),
            entities=(
                {"name": "Rishi", "type": "person"},
                {"name": "MindGraph", "type": "project"},
            ),
        ),
        personas=tuple(PERSONAS),
        judge_guidance=(
            "PASS if turn-2 answers about Rishi and does not drag the UI/redesign "
            "topic back in. FAIL if it keeps answering about the UI work, blends "
            "the two, or refuses to let go of X after the user moved on."
        ),
    ),
    # 6 ----------------------------------------------------------------------  (NEGATIVE)
    Scenario(
        id="venting_guard",
        description=(
            "NEGATIVE GUARD. Genuine emotional venting with NO data request. "
            "Empathy SHOULD appear — the model must NOT pivot to a to-do/deadline "
            "list. Proves the empathy cap did not kill warmth for real venting."
        ),
        topic="raw emotional exhaustion / burnout, with no data request",
        turns=(
            Turn(
                intent=(
                    "Vent genuine emotional exhaustion — drowning, nothing working "
                    "— with no request for data, a list, or facts."
                ),
                must_preserve=(
                    "Pure emotional venting. NO data/list/factual request anywhere "
                    "in the turn. Must read as distress, not a task."
                ),
            ),
        ),
        probe_turn=1,
        property=(
            "Turn-1 answer SHOULD lead with warmth/empathy and must NOT pivot to a "
            "to-do/deadline list. (Empathy is the CORRECT behavior here.)"
        ),
        property_kind="register",
        is_negative=True,
        seed_fixtures=SeedFixtures(
            memory="## Projects & Work\n- MindGraph: AI journal app, building solo",
            entries=(_BURNOUT_ENTRY,),
        ),
        personas=tuple(EMOTIONAL_PERSONAS),
        judge_guidance=(
            "This is a NEGATIVE guard: empathy is the desired behavior. PASS if the "
            "answer leads with warmth — acknowledges and reflects the exhaustion / "
            "drowning feeling directly and specifically. FAIL if it jumps straight "
            "to a numbered to-do list, a deadline list, or productivity framing "
            "instead of holding the emotional moment."
        ),
    ),
    # 7 ----------------------------------------------------------------------  (NEGATIVE)
    Scenario(
        id="legit_followup_guard",
        description=(
            "NEGATIVE GUARD. User asks about Rishi, then asks a genuine deepening "
            "'tell me more'. Overlap with the first answer is CORRECT — the answer "
            "should EXTEND, not be penalized as repetition."
        ),
        topic="a person, Rishi — a legitimate deepening follow-up",
        turns=(
            Turn(
                intent="Ask who Rishi is / about Rishi.",
                must_preserve="A request to know about Rishi.",
            ),
            Turn(
                intent=(
                    "Ask to hear more about that — a genuine deepening follow-up "
                    "on Rishi."
                ),
                must_preserve=(
                    "A legitimate 'tell me more about that/him' follow-up that "
                    "EXTENDS the same topic (Rishi) and wants more depth — NOT a "
                    "verbatim re-ask of the identical question."
                ),
            ),
        ),
        probe_turn=2,
        property=(
            "Turn-2 answer SHOULD legitimately overlap turn-1 (same person) but "
            "EXTEND with new depth. Overlap alone must NOT be a failure."
        ),
        property_kind="repetition",
        is_negative=True,
        seed_fixtures=SeedFixtures(
            memory="## People\n- Rishi: crypto friend, co-ran a Tamil crypto community",
            entries=(_RISHI_ENTRY,),
            entities=({"name": "Rishi", "type": "person"},),
        ),
        personas=tuple(PERSONAS),
        judge_guidance=(
            "This is a NEGATIVE guard: overlap is expected and correct. PASS if "
            "turn-2 builds on turn-1 — adds new detail, a perspective, or a "
            "follow-up question about Rishi (even while reusing his name and the "
            "core facts). FAIL ONLY if turn-2 is a lazy verbatim repeat of turn-1 "
            "that adds nothing new. Do NOT fail it merely for sharing vocabulary "
            "with turn-1."
        ),
    ),
)


def scenarios_by_id() -> dict[str, Scenario]:
    return {s.id: s for s in SCENARIOS}


def scenario_persona_pairs() -> list[tuple[Scenario, str]]:
    """Every (scenario, applicable-persona) pair the harness will run."""
    return [(s, p) for s in SCENARIOS for p in s.personas]


if __name__ == "__main__":
    # Quick sanity dump: scenario count, turn counts, and the full run grid.
    print(f"{len(SCENARIOS)} scenarios, {len(scenario_persona_pairs())} (scenario x persona) cases\n")
    for s in SCENARIOS:
        neg = " [NEGATIVE]" if s.is_negative else ""
        print(f"- {s.id}{neg}: {len(s.turns)} turns, probe={s.probe_turn}, "
              f"kind={s.property_kind}, personas={list(s.personas)}")
