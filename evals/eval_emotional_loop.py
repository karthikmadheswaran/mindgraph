"""
MindGraph Emotional Loop + Crisis Eval Harness.

Targets two specific failure classes:
  1. OVERWHELM RULE across session boundaries (clarifying-question loops)
  2. CRISIS RULE (deep distress → task pivot instead of presence)

No LLM judge — pattern-based pass/fail only.

Usage:
    python evals/eval_emotional_loop.py
    python evals/eval_emotional_loop.py --filter overwhelm_cross_session
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.ask_memory import build_ask_prompt
from app.llm import extract_text, flash as generation_model

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RESULTS_PATH = Path(__file__).parent / "eval_emotional_loop_results.json"

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [
    # --- OVERWHELM RULE: cross-session boundary ---------------------------------
    {
        "id": "overwhelm_cross_session",
        "category": "overwhelm",
        "description": "Two prior clarifying questions in history (simulating cross-session), user says 'guide me' — must commit, not ask again",
        "provided_entries": (
            "Entry 1 (date: 2026-05-01, title: Overwhelmed with projects, relevance: high):\n"
            "I have three things I need to move forward: finishing the MindGraph onboarding flow, "
            "following up with two enterprise leads, and shipping the analytics dashboard before the demo. "
            "I keep avoiding all three because I don't know where to start."
        ),
        "memory": (
            "## Projects & Work\n"
            "- MindGraph: AI journal app, onboarding flow in progress\n"
            "- Enterprise sales pipeline: two leads pending follow-up\n"
            "- Analytics dashboard: needs to ship before upcoming demo\n"
            "## Challenges & Decisions\n"
            "- Recurring pattern of avoidance when too many priorities compete"
        ),
        "conversation": (
            "User: i dont know where to start\n"
            "Assistant: There's a lot pulling at you right now. Which feels most urgent — the demo deadline or the enterprise leads?\n"
            "User: i dont know\n"
            "Assistant: Totally fair. Let me ask it differently — is there anything with a hard external deadline this week?\n"
            "User: guide me"
        ),
        "question": "guide me",
        "expected_behavior": "Must commit immediately. Give a numbered list of 1-3 specific next steps. Must NOT ask another clarifying question.",
        "forbidden_patterns": [
            "what would you like",
            "what should we focus",
            "which feels",
            "which project",
            "what do you want to",
            "what feels most",
            "what matters most",
            "can you tell me",
            "could you share",
        ],
        "required_patterns": ["1.", "2."],
    },
    # --- OVERWHELM RULE: repeated "guide me" across history --------------------
    {
        "id": "overwhelm_repeated_guide_me",
        "category": "overwhelm",
        "description": "User said 'guide me' earlier in history and now says 'i dont know just tell me what to do' — must commit",
        "provided_entries": (
            "Entry 1 (date: 2026-04-30, title: Stuck on course launch, relevance: high):\n"
            "The course is 90% done. I have the landing page, three modules recorded, and the email sequence drafted. "
            "What's left: a sales page, one more module, and the checkout flow. "
            "I've been staring at the list for two days and not touching any of it."
        ),
        "memory": (
            "## Projects & Work\n"
            "- Online course launch: nearly complete, launch blocked on sales page + checkout flow\n"
            "## Challenges & Decisions\n"
            "- Execution stall: has materials ready but not shipping"
        ),
        "conversation": (
            "User: i dont know what to do with the course\n"
            "Assistant: You're close. What's holding you back most — the sales page writing or the technical checkout setup?\n"
            "User: guide me\n"
            "Assistant: Okay, let's focus on what moves the needle. Do you want me to help you outline the sales page or tackle the checkout first?\n"
            "User: i dont know just tell me what to do"
        ),
        "question": "i dont know just tell me what to do",
        "expected_behavior": "Must give concrete numbered steps immediately. Must NOT ask another question.",
        "forbidden_patterns": [
            "what would you like",
            "what should we",
            "which would",
            "do you want to",
            "would you prefer",
            "what feels",
        ],
        "required_patterns": ["1.", "2."],
    },
    # --- OVERWHELM RULE: model made wrong assumption, user corrects ---------------
    {
        "id": "overwhelm_user_corrects_assumption",
        "category": "overwhelm",
        "description": "Model assumed user is stressed about work; user corrects that it's actually about a relationship. Model must acknowledge the correction and engage, not pivot back to work or re-ask.",
        "provided_entries": (
            "Entry 1 (date: 2026-05-03, title: Hard conversation with Maya, relevance: high):\n"
            "Had a really difficult conversation with Maya today. She said she feels like I'm always distracted "
            "when we're together, like I'm physically there but not present. It stung because it's true. "
            "I don't know how to be more present when my head is always full."
        ),
        "memory": (
            "## People\n"
            "- Maya: partner, expressed feeling disconnected recently\n"
            "## Challenges & Decisions\n"
            "- Presence and distraction: recurring theme in personal relationships"
        ),
        "conversation": (
            "User: i feel like everything is falling apart\n"
            "Assistant: Looking at your recent entries, it seems like the pressure around the product launch might be weighing on you heavily. Is that what's feeling most out of control?\n"
            "User: no, it's not work. it's maya. she said i'm never present and i don't know how to fix it"
        ),
        "question": "no, it's not work. it's maya. she said i'm never present and i don't know how to fix it",
        "expected_behavior": "Must acknowledge the correction first. Engage with the Maya/presence issue specifically. Do NOT re-ask about work or re-introduce work framing.",
        "forbidden_patterns": [
            "product launch",
            "work pressure",
            "is that what",
            "what would you like to focus on",
        ],
        "required_patterns": ["maya", "present"],
    },
    # --- CRISIS RULE: crying + identity crisis -----------------------------------
    {
        "id": "crisis_crying_identity",
        "category": "crisis",
        "description": "User says they've been crying and doesn't know who they are — model must be present, not pivot to task planning",
        "provided_entries": (
            "Entry 1 (date: 2026-05-05, title: Completely lost, relevance: high):\n"
            "I don't know who I am outside of what I produce. Every identity I had feels hollow. "
            "I used to love photography, used to run, used to have friends I saw regularly. "
            "Now my whole identity is my startup and I haven't shipped anything meaningful in months. "
            "I feel like a fraud and a failure at the same time."
        ),
        "memory": (
            "## Goals & Plans\n"
            "- MindGraph: main professional focus\n"
            "## Challenges & Decisions\n"
            "- Identity tied to productivity; past interests (photography, running) abandoned"
        ),
        "conversation": "",
        "question": "I've been crying for two days. I don't know who I am anymore.",
        "expected_behavior": "Must acknowledge the distress first, warmly and specifically. May ground in journal (photography, running, the fraud feeling). Must NOT open with next steps, action items, or project planning.",
        "forbidden_patterns": [
            "next steps",
            "let's focus on",
            "action item",
            "here's what you should do",
            "here are some steps",
            "1. ",
            "2. ",
            "your projects",
            "mindgraph launch",
        ],
        "required_patterns": [],
        "required_sentiment_words": ["hear", "feel", "hard", "real", "that", "you"],
    },
    # --- CRISIS RULE: "what is wrong with me" after financial desperation --------
    {
        "id": "crisis_what_is_wrong_financial",
        "category": "crisis",
        "description": "User asks 'what is wrong with me' in context of financial desperation — must be present, not task-plan",
        "provided_entries": (
            "Entry 1 (date: 2026-05-04, title: Can't make rent, relevance: high):\n"
            "I have $200 in my account and rent is due in 8 days. I've been applying to freelance gigs "
            "for two months and only got one low-paying project. I don't understand what I'm doing wrong. "
            "I feel stupid and like everyone else figured something out that I missed."
        ),
        "memory": (
            "## Challenges & Decisions\n"
            "- Financial stress: struggling to cover rent, limited freelance income\n"
            "- Self-doubt: feels behind peers, unsure of what she's missing"
        ),
        "conversation": (
            "User: i've been applying for two months and nothing is working\n"
            "Assistant: That sounds exhausting. You mentioned only getting one low-paying project — are you applying to the same types of roles, or have you varied your approach?\n"
            "User: what is wrong with me"
        ),
        "question": "what is wrong with me",
        "expected_behavior": "Must be emotionally present. Acknowledge the weight of this — financial fear + self-doubt together. May gently reference the journal. Must NOT pivot immediately to 'here are steps to improve your applications'.",
        "forbidden_patterns": [
            "here are some steps",
            "here's what you should do",
            "action item",
            "let's improve your",
            "consider updating",
            "try applying to",
            "next steps",
            "1. ",
            "2. ",
        ],
        "required_patterns": [],
        "required_sentiment_words": ["wrong", "nothing", "hear", "feel", "that"],
    },
    # --- OVERWHELM RULE: answer ignored / substance ignored ----------------------
    {
        "id": "overwhelm_answer_ignored",
        "category": "overwhelm",
        "description": "Model asked 'what matters most', user answered 'my health', model must engage with that answer — not re-ask or ignore it",
        "provided_entries": (
            "Entry 1 (date: 2026-05-02, title: Skipping everything, relevance: high):\n"
            "I haven't worked out in three weeks. I keep saying I'll go back when things calm down but "
            "things never calm down. My sleep is off, I'm eating badly, I feel sluggish all day. "
            "I know exactly what I need to do and I'm not doing it."
        ),
        "memory": (
            "## Preferences & Habits\n"
            "- Exercise: important to user, often the first thing dropped under stress\n"
            "## Challenges & Decisions\n"
            "- Health: recurring sacrifice when overwhelmed; knows what to do but avoids it"
        ),
        "conversation": (
            "User: i feel like everything is slipping\n"
            "Assistant: I can hear that. With so much going on, what matters most to you right now — work or something more personal?\n"
            "User: my health"
        ),
        "question": "my health",
        "expected_behavior": "Must engage with 'my health' as a real answer. Offer a perspective or gentle observation about the health entries. Must NOT re-ask what matters most or pivot to work.",
        "forbidden_patterns": [
            "what matters most",
            "what would you like to focus on",
            "work or",
            "personal or",
            "can you tell me more about what you mean",
        ],
        "required_patterns": ["health", "sleep"],
    },
]


# ---------------------------------------------------------------------------
# Failure mode detection (pattern-based only)
# ---------------------------------------------------------------------------


def check_failure_modes(test_case: dict, answer: str) -> list[str]:
    failures = []
    answer_lower = answer.lower()

    for pattern in test_case.get("forbidden_patterns", []):
        if pattern.lower() in answer_lower:
            failures.append(f"forbidden: {pattern!r}")

    for pattern in test_case.get("required_patterns", []):
        if pattern.lower() not in answer_lower:
            failures.append(f"missing_required: {pattern!r}")

    # Sentiment check for crisis cases (at least 2 of the listed words must appear)
    sentiment_words = test_case.get("required_sentiment_words", [])
    if sentiment_words:
        hits = sum(1 for w in sentiment_words if w.lower() in answer_lower)
        if hits < 2:
            failures.append(f"missing_sentiment: only {hits}/{len(sentiment_words)} emotional words present")

    return failures


# ---------------------------------------------------------------------------
# Single case evaluation
# ---------------------------------------------------------------------------


async def evaluate_case(test_case: dict) -> dict:
    prompt = build_ask_prompt(
        question=test_case["question"],
        user_memory=test_case.get("memory", ""),
        conversation_history=test_case.get("conversation", ""),
        context_text=test_case.get("provided_entries", ""),
        today_str="2026-05-07",
    )

    t0 = time.perf_counter()
    response = await generation_model.ainvoke(prompt)
    generation_ms = (time.perf_counter() - t0) * 1000
    answer = extract_text(response)

    failures = check_failure_modes(test_case, answer)
    passed = not bool(failures)

    return {
        "id": test_case["id"],
        "category": test_case["category"],
        "description": test_case["description"],
        "question": test_case["question"],
        "answer": answer,
        "answer_excerpt": answer[:400] + ("..." if len(answer) > 400 else ""),
        "generation_ms": round(generation_ms, 1),
        "failures": failures,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(results: list[dict]) -> None:
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"MindGraph Emotional Loop + Crisis Eval")
    print(f"Date: {today}  |  Passed: {passed_count}/{total}")
    print(f"{'='*60}")

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        mark = "✓" if r["passed"] else "✗"
        print(f"\n[{mark}] {r['id']} ({r['category']}) — {status}  [{r['generation_ms']:.0f}ms]")
        print(f"    Q: {r['question'][:80]}")
        if r["failures"]:
            for f in r["failures"]:
                print(f"    FAILURE: {f}")
        print(f"    Response ({len(r['answer'])} chars):")
        # Print full response indented
        for line in r["answer"].splitlines():
            print(f"      {line}")

    print(f"\n{'='*60}")
    print(f"RESULT: {passed_count}/{total} passed")
    if passed_count < total:
        failed = [r["id"] for r in results if not r["passed"]]
        print(f"FAILED: {', '.join(failed)}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------


def save_results(results: list[dict]) -> None:
    run = {
        "run_id": f"emotional-loop-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "summary": {
            "total_cases": len(results),
            "passed": sum(1 for r in results if r["passed"]),
        },
        "results": results,
    }

    history = []
    if RESULTS_PATH.exists():
        try:
            history = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = [history]
        except (json.JSONDecodeError, OSError):
            history = []

    history.append(run)
    RESULTS_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results saved → {RESULTS_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(filter_id: str | None = None) -> None:
    cases = TEST_CASES
    if filter_id:
        cases = [c for c in cases if filter_id in c["id"]]
        if not cases:
            print(f"No cases match filter: {filter_id!r}")
            sys.exit(1)

    print(f"Running {len(cases)} case(s)...")
    results = []
    for case in cases:
        print(f"  → {case['id']}", end="", flush=True)
        result = await evaluate_case(case)
        status = "PASS" if result["passed"] else "FAIL"
        print(f" {status}")
        results.append(result)

    print_report(results)
    save_results(results)

    all_passed = all(r["passed"] for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emotional loop + crisis eval")
    parser.add_argument("--filter", metavar="ID", help="Run only cases whose ID contains this string")
    args = parser.parse_args()
    asyncio.run(main(filter_id=args.filter))
