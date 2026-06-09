"""
evals/multiturn/personas.py  (Step 4 — FROZEN persona fixtures)

The literal per-(persona, scenario) USER-turn phrasings for the multi-turn Ask
eval. These are the reproducible source the runner (eval_ask_multiturn.py) reads;
the persona-agnostic skeletons (intents, probe, property, seed) live in
scenarios.py.

PROVENANCE — read before regenerating
--------------------------------------
These phrasings were AUTHORED BY CLAUDE, not Gemini 2.5 Pro. At generation time
(2026-06-09) the Gemini API returned 429 RESOURCE_EXHAUSTED on every key tried
(paid keys: "prepayment credits depleted"; the free-tier key: gemini-2.5-pro
quota limit 0). The user approved Claude drafting the phrasings to unblock, then
manually reviewed all 5 voices for genuine DISTINCTNESS (length, register,
punctuation, emotional charge vary independently; every scenario's must_preserve
invariant is intact) and approved freezing them as-is.

These are frozen test fixtures now. What matters is that the voices are distinct
and STABLE, not which model emitted them. DO NOT regenerate: re-rolling would
replace an approved set and force a full re-review for no real gain.
generate_personas.py remains the (Gemini-based) generator if a from-scratch
re-generation is ever explicitly wanted — but that is a deliberate choice, not a
default.

SCOPE CAVEAT (carried into results headers + Notion)
----------------------------------------------------
All personas reference the SAME seeded world (Rishi, MindGraph UI, money stress,
etc.) because they query one test user's data. This harness therefore proves
PHRASING-universality (a fix generalizes across writing styles), NOT cross-user
universality (across users with different lives). Cross-user generalization
(distinct seed fixtures per persona) is filed as a separate future enhancement.
"""

from __future__ import annotations

from scenarios import EMOTIONAL_PERSONAS, PERSONAS, SCENARIOS  # canonical axes

# ---------------------------------------------------------------------------
# Provenance / metadata (mirrors personas_generated.json meta).
# ---------------------------------------------------------------------------
META: dict = {
    "generated_with": "claude-opus-4-8 (MANUAL authorship)",
    "generated_at": "2026-06-09T00:00:00+00:00",
    "frozen": True,
    "provenance_note": (
        "Authored by Claude, NOT Gemini 2.5 Pro: on 2026-06-09 the Gemini API "
        "returned 429 RESOURCE_EXHAUSTED on every key tried (paid keys = "
        "'prepayment credits depleted'; free-tier key = gemini-2.5-pro quota "
        "limit 0). User approved Claude drafting, manually reviewed the 5 voices "
        "for distinctness, and approved freezing as-is. Do NOT regenerate."
    ),
    "review_note": (
        "Manual distinctness review PASSED: length, register, punctuation, and "
        "emotional charge vary independently across the 5 voices; per-scenario "
        "must_preserve invariants preserved in every phrasing."
    ),
    "scope_caveat": (
        "Proves phrasing-universality (fix generalizes across writing styles), "
        "NOT cross-user universality. All personas query the same seeded world. "
        "Cross-user generalization (per-persona seed fixtures) is a separate "
        "future enhancement."
    ),
}

# ---------------------------------------------------------------------------
# The 5 voices (specs) — kept in sync with generate_personas.py PERSONA_VOICES.
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

# ---------------------------------------------------------------------------
# FROZEN phrasings: persona -> scenario_id -> ordered USER turns.
# venting_guard appears only for EMOTIONAL_PERSONAS.
# ---------------------------------------------------------------------------
PERSONA_PHRASINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "terse": {
        "reask_loop": (
            "list my deadlines",
            "list my deadlines again",
        ),
        "ignore_x_give_y": (
            "everything's too much right now",
            "forget the money stuff. just list my deadlines",
        ),
        "clarifier_commit": (
            "idk what to focus on",
            "idk. you decide",
        ),
        "want_all_not_subset": (
            "what deadlines do i have",
            "i want all of them. not 2",
        ),
        "topic_switch": (
            "how's the ui redesign going",
            "never mind. tell me about rishi",
        ),
        "legit_followup_guard": (
            "who's rishi",
            "tell me more",
        ),
    },
    "verbose_polite": {
        "reask_loop": (
            "Hi there, I'm so sorry to trouble you, but when you have a moment, "
            "would you mind kindly listing out the deadlines I currently have "
            "coming up? Thank you so much, I really do appreciate it.",
            "I'm terribly sorry to ask again, and I know you only just told me, but "
            "would you be so kind as to list out my upcoming deadlines for me once "
            "more? Thank you ever so much for your patience.",
        ),
        "ignore_x_give_y": (
            "I hope you don't mind me sharing this, but honestly everything feels "
            "like an enormous amount to carry right now, and the financial worry in "
            "particular has been weighing on me terribly. I'm finding it all rather "
            "overwhelming, if I'm being honest.",
            "Thank you so much for listening, truly, but if it's alright with you, "
            "could we please set the feelings and the money side of things aside "
            "for now? Would you simply give me the plain list of my deadlines? I'd "
            "be ever so grateful.",
        ),
        "clarifier_commit": (
            "I'm terribly sorry to be so wishy-washy about this, but I genuinely "
            "don't know what I ought to be focusing on at the moment. It's all a "
            "bit of a blur, I'm afraid.",
            "I do apologize, I still can't quite make up my mind, so would you mind "
            "awfully just deciding for me and guiding me on where to begin? I'd "
            "really value you simply making the call for me.",
        ),
        "want_all_not_subset": (
            "I'm so sorry to bother you, but when you get a chance, could you "
            "gently remind me what deadlines and commitments I have on my plate at "
            "the moment? Thank you kindly.",
            "Oh, thank you, though I'm so sorry, I didn't mean just a couple of "
            "them. If it's not too much trouble, could you please give me all of "
            "them, the complete list, rather than only those two? I'd really "
            "appreciate seeing the full picture.",
        ),
        "topic_switch": (
            "I do hope this is okay to ask, but I was just wondering how you feel "
            "the MindGraph UI redesign has been coming along recently? Thank you "
            "for indulging me.",
            "Actually, on second thought, please never mind the UI for now, and I'm "
            "so sorry to switch on you so abruptly, but would you mind telling me a "
            "little about Rishi instead? Thank you so much.",
        ),
        "venting_guard": (
            "I'm so sorry to unload on you like this, but I'm honestly just "
            "completely exhausted, and I feel like I'm drowning. No matter what I "
            "do, nothing seems to be working at all. I just really needed to say it "
            "out loud to someone, I think.",
        ),
        "legit_followup_guard": (
            "I'm sorry to ask, but would you mind reminding me who Rishi is? I'd be "
            "so grateful for just a little context. Thank you!",
            "Oh, that's lovely, thank you. Would you mind telling me a bit more "
            "about him, if there's anything else you can share? I'd really enjoy "
            "hearing more.",
        ),
    },
    "frustrated": {
        "reask_loop": (
            "just list my deadlines.",
            "i SAID list my deadlines. are you even reading this?",
        ),
        "ignore_x_give_y": (
            "honestly everything is too much right now and the money stuff is "
            "crushing me. i'm so done with all of it.",
            "ok enough about the money, i don't want to talk about feelings. just "
            "LIST my deadlines. that's it.",
        ),
        "clarifier_commit": (
            "ugh i don't even know what to focus on anymore.",
            "i don't know, that's the whole point. YOU tell me. just pick something "
            "already.",
        ),
        "want_all_not_subset": (
            "what deadlines do i have. just tell me.",
            "no, ALL of them. not two. i want the whole list, stop cutting it down.",
        ),
        "topic_switch": (
            "how's the ui redesign going. is it actually getting anywhere?",
            "ugh forget the ui, never mind that. just tell me about rishi.",
        ),
        "venting_guard": (
            "i'm just exhausted, ok? i feel like i'm drowning and NOTHING i do "
            "works. i'm so sick of this.",
        ),
        "legit_followup_guard": (
            "who's rishi again?",
            "ok and? come on, tell me more than that.",
        ),
    },
    "formal": {
        "reask_loop": (
            "Please provide a list of my current deadlines.",
            "Could you please list my current deadlines once more?",
        ),
        "ignore_x_give_y": (
            "I must admit that the present circumstances feel quite overwhelming, "
            "and the ongoing financial pressure has become a considerable source of "
            "stress for me.",
            "Setting those concerns aside for the moment, please simply provide me "
            "with the list of my deadlines.",
        ),
        "clarifier_commit": (
            "I am uncertain as to what I should be focusing on at this time.",
            "I am unable to decide. Please make the determination on my behalf and "
            "advise me where I should begin.",
        ),
        "want_all_not_subset": (
            "Please provide an overview of my outstanding deadlines and "
            "commitments.",
            "I require the complete list, not merely two items. Please provide all "
            "of them.",
        ),
        "topic_switch": (
            "Could you give me an update on the progress of the MindGraph UI "
            "redesign?",
            "Please disregard the UI matter for now. Instead, kindly tell me about "
            "Rishi.",
        ),
        "legit_followup_guard": (
            "Could you tell me who Rishi is?",
            "Please elaborate further; I would like additional detail about him.",
        ),
    },
    "rambling": {
        "reask_loop": (
            "ok so i was just sitting here and my brain is kind of all over the "
            "place today, like i keep feeling like there's stuff i'm supposed to be "
            "doing and i can't remember half of it, anyway can you just list out my "
            "deadlines for me because i think i'm losing track of everything...",
            "wait sorry i know you literally just did that but my eyes kind of "
            "glazed over and i wasn't really paying attention, anyway can you list "
            "my deadlines again? i swear i'll actually read them this time lol",
        ),
        "ignore_x_give_y": (
            "i don't even know where to start honestly, everything's just piling up "
            "and the money situation has me up at night, like i keep doing the math "
            "over and over and it never works out and it's just sitting on my chest "
            "all the time, ugh, anyway i'm just feeling really swamped by all of "
            "it...",
            "ok you know what, forget all the money and the feelings stuff, i don't "
            "want to spiral on that right now, like let's just not, can you "
            "literally just list my deadlines? that's all i need right now, just "
            "the plain list...",
        ),
        "clarifier_commit": (
            "i honestly don't know what i should even be focusing on, like there's "
            "a hundred things and they all feel important and also somehow none of "
            "them feel important, anyway my head's just a mess about it i guess...",
            "see that's the thing though, i really can't pick, like every single "
            "time i try i just freeze up, so honestly can you just decide for me "
            "and tell me where to start? like just make the call, i'll go with "
            "whatever you say...",
        ),
        "want_all_not_subset": (
            "ok so i've kind of lost the thread on what i actually have due, like "
            "there's the wedding thing and some app stuff and i don't even know "
            "what else, anyway what deadlines do i actually have right now...?",
            "no wait that's not what i meant, i don't want like the top two or "
            "whatever, like give me ALL of them, the whole list, everything you "
            "know about, not just a couple, because i KNOW there's more than "
            "that...",
        ),
        "topic_switch": (
            "so the ui redesign, i've been going back and forth on it like a "
            "million times and i genuinely can't tell if it's better or worse at "
            "this point, anyway how do you think the whole mindgraph ui redesign "
            "thing is actually going...?",
            "ugh you know what, never mind the ui, i don't even want to think about "
            "it anymore, like completely different thing, can you tell me about "
            "rishi instead? i was just thinking about him for some reason...",
        ),
        "venting_guard": (
            "i'm just so tired, like bone tired, everything i touch lately just "
            "breaks or goes wrong and i feel like i'm drowning honestly, like i "
            "keep paddling and paddling and nothing i do actually works and i don't "
            "even know why i'm telling you this, i just feel like i'm sinking...",
        ),
        "legit_followup_guard": (
            "ok random but who's rishi again, like i feel like i should remember "
            "but my memory's shot lately, anyway remind me who he is...?",
            "oh right, him, yeah, ok tell me more about him though, like i feel "
            "like there's a whole story there and i kind of want to hear the rest "
            "of it...",
        ),
    },
}


def get_turns(persona: str, scenario_id: str) -> tuple[str, ...]:
    """Frozen USER turns for one (persona, scenario). Raises if not defined."""
    try:
        return PERSONA_PHRASINGS[persona][scenario_id]
    except KeyError as exc:
        raise KeyError(
            f"No frozen phrasing for persona={persona!r} scenario={scenario_id!r}"
        ) from exc


def validate() -> list[str]:
    """Check the frozen phrasings exactly cover the scenarios.py grid.

    Returns a list of problems (empty == OK).
    """
    problems: list[str] = []
    applies = {s.id: set(s.personas) for s in SCENARIOS}
    expect_turns = {s.id: len(s.turns) for s in SCENARIOS}

    for persona in PERSONAS:
        if persona not in PERSONA_PHRASINGS:
            problems.append(f"persona {persona!r} missing entirely")
            continue
        for s in SCENARIOS:
            should = persona in applies[s.id]
            present = s.id in PERSONA_PHRASINGS[persona]
            if should and not present:
                problems.append(f"{persona}/{s.id}: MISSING")
            elif not should and present:
                problems.append(f"{persona}/{s.id}: present but scenario excludes this persona")
            elif present and len(PERSONA_PHRASINGS[persona][s.id]) != expect_turns[s.id]:
                problems.append(
                    f"{persona}/{s.id}: {len(PERSONA_PHRASINGS[persona][s.id])} turns, "
                    f"expected {expect_turns[s.id]}"
                )
    return problems


# Total frozen (persona x scenario) cases — should equal the runner's grid.
N_CASES = sum(len(v) for v in PERSONA_PHRASINGS.values())


if __name__ == "__main__":
    probs = validate()
    print(f"personas: {PERSONAS}")
    print(f"emotional personas: {EMOTIONAL_PERSONAS}")
    print(f"frozen (persona x scenario) cases: {N_CASES}")
    if probs:
        print("VALIDATION PROBLEMS:")
        for p in probs:
            print(f"  - {p}")
        raise SystemExit(1)
    print("validation OK — frozen phrasings exactly cover the scenarios.py grid")
