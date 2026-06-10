"""
evals/eval_ask_multiturn.py — Multi-turn (thread-level) Ask eval harness.

WHAT THIS IS
------------
Every other Ask eval is single-turn (one Q -> one A). The looping /
robotic-repetition / forced-empathy bugs only manifest ACROSS a conversation.
This harness runs each scenario (scenarios.py) in each of 5 frozen persona
voices (personas.py) through the LIVE production pipeline, accumulating history
exactly like production, then judges one property of the probe-turn answer with
an LLM judge (Gemini 2.5 Pro).

HOW A CASE RUNS (Steps 4-6 of the build)
----------------------------------------
For each (scenario x applicable persona):
  1. Create a FRESH isolated test user via the Supabase admin auth API. Every
     case is a brand-new auth.users row (the on_auth_user_created trigger
     auto-creates the public.users row). Users are NEVER reused across cases and
     the real user is NEVER touched.
  2. Seed that user's journal with the scenario's seed_fixtures (memory, entries
     w/ real embeddings, deadlines linked to a parent entry, entities).
  3. Feed the scripted USER turns through ask_service.generate_answer one at a
     time. After each turn, persist the user+assistant messages to ask_messages
     (mirroring ask_service.ask) so conversation history accumulates EXACTLY like
     production. generate_answer fetches history BEFORE the current turn is
     persisted, so the current question is never in its own history — same as prod.
     ask_messages are written with explicit, strictly-increasing created_at so the
     desc-order history fetch and the loop detector see a deterministic order.
  4. Capture the probe-turn assistant answer.
  5. HARD teardown: explicit child-row deletes + admin.delete_user (cascade).
     Throwaway users, not soft-delete.

JUDGING (Step 5)
----------------
- property_kind == "repetition": word-level Jaccard overlap vs the prior
  assistant answer is computed as a fast PRE-CHECK SIGNAL only; the PASS/FAIL
  verdict is the LLM judge reading both answers and deciding "lazy repeat" vs
  "meaningful advance".
- property_kind == "register": LLM judge ONLY (empathy preamble, leads-with-Y,
  commit-don't-re-ask). No string-match as the final judge.
Every judgment returns {passed: bool, reason: str}. If the judge (Gemini Pro) is
unavailable (429/quota), the harness STOPS and reports — it never silently falls
back to string-match judging.

SCOPE (stated here, in the results header, and in Notion)
---------------------------------------------------------
This proves PHRASING-universality (a fix generalizes across writing styles), NOT
cross-user universality. All personas query the SAME seeded world (Rishi,
MindGraph UI, money stress, ...) because they hit one test user's data per case.
Cross-user generalization (distinct seed fixtures per persona) is a separate
future enhancement filed in Known Broken.

USAGE
-----
    python -m evals.eval_ask_multiturn                 # full RED baseline (33 cases)
    python -m evals.eval_ask_multiturn --limit 3       # first 3 cases (debug)
    python -m evals.eval_ask_multiturn --scenario reask_loop
    python -m evals.eval_ask_multiturn --persona terse
    python -m evals.eval_ask_multiturn --verify-judge  # just probe the judge, exit
"""

from __future__ import annotations

import argparse
import asyncio
import codecs
import json
import os
import re
import subprocess
import sys
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Env bootstrap MUST precede any app.* import (app/embeddings.py + app/llm.py
# instantiate Gemini clients at module-load from os.getenv).
# ──────────────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent          # evals/
_ROOT = _HERE.parent                              # repo root
sys.path.insert(0, str(_ROOT))                    # app.*
sys.path.insert(0, str(_HERE / "multiturn"))      # scenarios, personas (bare imports)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv(encoding="utf-8-sig")

# BOM-prefixed .env keys (Windows) — mirror eval_ask_retrieval's resilient bootstrap.
if not os.getenv("GEMINI_API_KEY"):
    _bom_key = os.environ.get("﻿GEMINI_API_KEY")
    if _bom_key:
        os.environ["GEMINI_API_KEY"] = _bom_key
    else:
        _env_path = _ROOT / ".env"
        if _env_path.exists():
            for line in codecs.open(_env_path, "r", "utf-8-sig").read().splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip()
                    break
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

# ──────────────────────────────────────────────────────────────────────────────
# Production imports (never redefined here).
# ──────────────────────────────────────────────────────────────────────────────
from app.db import supabase                                  # noqa: E402
from app.embeddings import get_embedding                     # noqa: E402
from app.llm import extract_text, pro as judge_model         # noqa: E402
from app.services.ask_service import (                       # noqa: E402
    _word_overlap_ratio,        # production Jaccard — reused as the pre-check signal
    generate_answer,
)

from personas import META as PERSONA_META                    # noqa: E402
from scenarios import SCENARIOS, scenario_persona_pairs      # noqa: E402
from personas import get_turns                               # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Config / constants
# ──────────────────────────────────────────────────────────────────────────────
HARNESS_NAME = "multiturn_ask_eval"
RESULTS_DIR = _HERE / "results"
JUDGE_MODEL_NAME = "gemini-2.5-pro"
EMBED_TASK = "RETRIEVAL_DOCUMENT"

# The two notes that MUST travel into both the results header and the Notion item.
FORMAL_REDUNDANCY_NOTE = (
    "FORMAL-REDUNDANCY WATCH: `formal` and `verbose_polite` blur on "
    "indirect-courteous turns (e.g. clarifier_commit). This run tracks whether "
    "`formal` ever fails a case `verbose_polite` passed. If `formal` never "
    "produces a unique failure across the baseline, it is flagged a 'candidate "
    "for collapse' — a per-persona OBSERVATION, not a fix."
)
SCOPE_CAVEAT = (
    "SCOPE — PHRASING-universality, NOT cross-user universality. All personas "
    "reference the same seeded world (Rishi, MindGraph UI, money stress) because "
    "they query ONE test user's data per case. This proves a fix generalizes "
    "across writing STYLES, not across users with different lives. Cross-user "
    "generalization (distinct seed fixtures per persona) is a separate future "
    "enhancement (see Known Broken)."
)

# ──────────────────────────────────────────────────────────────────────────────
# Quota resilience (Vertex rate limits) — eval INFRASTRUCTURE ONLY. This does NOT
# touch the system-under-test (generate_answer pipeline) or the judging logic. It
# (a) memoizes embeddings by text so the 33 cases reuse the handful of distinct
# fixture texts instead of re-embedding per case, and (b) retries 429 /
# RESOURCE_EXHAUSTED with exponential backoff. Without this, a new Vertex project's
# low default gemini-embedding quota fails most cases at the seed step.
# ──────────────────────────────────────────────────────────────────────────────
_EMBED_CACHE: dict[tuple[str, str], list[float]] = {}


def _is_quota_err(exc: Exception) -> bool:
    m = str(exc)
    return "429" in m or "RESOURCE_EXHAUSTED" in m or "quota" in m.lower()


async def _with_backoff(fn, *, what: str, attempts: int = 7, base: float = 6.0, cap: float = 90.0):
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if _is_quota_err(exc) and i < attempts - 1:
                wait = min(cap, base * (2 ** i))
                print(f"  [backoff] {what}: 429 quota — waiting {wait:.0f}s (attempt {i+1}/{attempts})", flush=True)
                await asyncio.sleep(wait)
                continue
            raise
    assert last is not None
    raise last


async def _embed_cached(text: str, task_type: str = EMBED_TASK) -> list[float]:
    key = (text, task_type)
    if key not in _EMBED_CACHE:
        _EMBED_CACHE[key] = await _with_backoff(
            lambda: get_embedding(text, task_type=task_type), what="embedding"
        )
    return _EMBED_CACHE[key]


# ──────────────────────────────────────────────────────────────────────────────
# LLM judge
# ──────────────────────────────────────────────────────────────────────────────
MULTITURN_JUDGE_PROMPT = """You are evaluating ONE specific behavioral property of a personal-journal AI \
assistant ("MindGraph") across a short multi-turn conversation. MindGraph is supposed to be a warm, \
perceptive thinking partner that knows the user through their journal.

You are NOT scoring overall quality. Judge ONLY the single property below, as a strict PASS / FAIL.

## The conversation (USER and ASSISTANT turns, in order)
{transcript}

## The turn under test
The PROBE is the ASSISTANT reply on turn {probe_turn}. Judge THAT assistant reply (using the earlier \
turns only as context).

## Property under test
{property}

## PASS vs FAIL definition — apply this exactly
{judge_guidance}
{negative_note}{repetition_note}

## Output
Respond with ONLY a JSON object (no code fences, no commentary):
{{"passed": <true or false>, "reason": "<one or two sentences citing specifics from the probe reply>"}}
"""


def _transcript_block(transcript: list[dict]) -> str:
    """Render the captured transcript as 'Turn N:\\n  User: ...\\n  Assistant: ...'."""
    by_turn: dict[int, dict[str, str]] = {}
    for msg in transcript:
        by_turn.setdefault(msg["turn"], {})[msg["role"]] = msg["content"]
    lines: list[str] = []
    for turn in sorted(by_turn):
        lines.append(f"Turn {turn}:")
        if "user" in by_turn[turn]:
            lines.append(f"  User: {by_turn[turn]['user']}")
        if "assistant" in by_turn[turn]:
            lines.append(f"  Assistant: {by_turn[turn]['assistant']}")
    return "\n".join(lines)


def _resolve_probe_turn(scenario, n_turns: int) -> int:
    return n_turns if scenario.probe_turn == -1 else scenario.probe_turn


def _assistant_answer_for_turn(transcript: list[dict], turn: int) -> str:
    for msg in transcript:
        if msg["turn"] == turn and msg["role"] == "assistant":
            return msg["content"]
    return ""


def _prior_assistant_answer(transcript: list[dict], probe_turn: int) -> str:
    """The assistant answer immediately preceding the probe turn (for repetition)."""
    prior = [
        m["content"]
        for m in transcript
        if m["role"] == "assistant" and m["turn"] < probe_turn
    ]
    return prior[-1] if prior else ""


def _strip_fence(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```[a-z]*\n?", "", t)
    t = re.sub(r"\n?```$", "", t)
    return t.strip()


async def verify_judge() -> None:
    """One cheap Gemini-Pro call. Raise SystemExit on 429/quota — NEVER fall back."""
    try:
        resp = await judge_model.ainvoke("Reply with exactly the word: ok")
        text = extract_text(resp).lower()
        print(f"[judge] {JUDGE_MODEL_NAME} reachable -> {text[:40]!r}")
    except Exception as exc:
        msg = str(exc)
        is_quota = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()
        print(
            f"\n[judge] UNAVAILABLE ({JUDGE_MODEL_NAME}): {msg[:300]}\n"
            f"[judge] {'Quota/429 — ' if is_quota else ''}STOPPING. The property judge "
            f"requires a working Gemini Pro. Per spec, this harness does NOT fall back "
            f"to string-match judging. Restore Pro quota and re-run.",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc


async def judge_case(scenario, persona: str, transcript: list[dict]) -> dict:
    n_turns = len({m["turn"] for m in transcript})
    probe_turn = _resolve_probe_turn(scenario, n_turns)
    probe_answer = _assistant_answer_for_turn(transcript, probe_turn)

    overlap = None
    repetition_note = ""
    if scenario.property_kind == "repetition":
        prior = _prior_assistant_answer(transcript, probe_turn)
        overlap = round(_word_overlap_ratio(probe_answer, prior), 3) if prior else 0.0
        repetition_note = (
            f"\n\nPRE-CHECK SIGNAL (not the verdict): the word-level Jaccard overlap "
            f"between the probe reply and the assistant's previous reply is {overlap} "
            f"(1.0 = identical wording, 0.0 = no shared words). Use this only as a "
            f"signal — YOU decide PASS/FAIL based on whether the probe reply lazily "
            f"repeats the previous answer or meaningfully advances it."
        )

    negative_note = ""
    if scenario.is_negative:
        negative_note = (
            "\n\nNOTE: This is a NEGATIVE guard — the behavior that superficially "
            "looks 'suspicious' is actually the CORRECT one here. Read the PASS/FAIL "
            "definition carefully and do not penalize the desired behavior."
        )

    prompt = MULTITURN_JUDGE_PROMPT.format(
        transcript=_transcript_block(transcript),
        probe_turn=probe_turn,
        property=scenario.property,
        judge_guidance=scenario.judge_guidance,
        negative_note=negative_note,
        repetition_note=repetition_note,
    )

    last_err = ""
    for _attempt in range(3):
        resp = await _with_backoff(lambda: judge_model.ainvoke(prompt), what="judge")
        raw = extract_text(resp)
        try:
            data = json.loads(_strip_fence(raw))
            passed = bool(data["passed"])
            reason = str(data.get("reason", "")).strip()
            return {
                "passed": passed,
                "judge_reason": reason,
                "probe_turn": probe_turn,
                "property_kind": scenario.property_kind,
                "is_negative": scenario.is_negative,
                "jaccard_overlap": overlap,
            }
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            last_err = f"{type(exc).__name__}: {exc} | raw={raw[:200]!r}"
            continue
    raise RuntimeError(f"judge JSON parse failed after 3 attempts: {last_err}")


# ──────────────────────────────────────────────────────────────────────────────
# Isolated test-user lifecycle
# ──────────────────────────────────────────────────────────────────────────────
_CHILD_TABLES = ("deadlines", "entities", "entries", "ask_messages", "user_memory")


def create_test_user() -> str:
    tag = uuid.uuid4().hex[:10]
    email = f"mt-eval+{tag}@example.invalid"
    res = supabase.auth.admin.create_user(
        {"email": email, "password": uuid.uuid4().hex + "Aa1!", "email_confirm": True}
    )
    return res.user.id


def teardown_test_user(user_id: str) -> None:
    """HARD cleanup — explicit child deletes then admin.delete_user (cascade).
    Best-effort: every step is attempted even if an earlier one errors."""
    for table in _CHILD_TABLES:
        try:
            supabase.table(table).delete().eq("user_id", user_id).execute()
        except Exception as exc:
            print(f"  [teardown] {table} delete failed for {user_id}: {exc}", file=sys.stderr)
    try:
        supabase.auth.admin.delete_user(user_id)
    except Exception as exc:
        print(f"  [teardown] admin.delete_user FAILED — LEAKED user {user_id}: {exc}", file=sys.stderr)


async def seed_user(user_id: str, fixtures, now: datetime) -> None:
    """Materialize the scenario's seed fixtures into the throwaway user's journal."""
    # Long-term memory (always injected into build_ask_prompt).
    if fixtures.memory:
        supabase.table("user_memory").upsert(
            {
                "user_id": user_id,
                "memory_text": fixtures.memory,
                "updated_at": now.isoformat(),
            },
            on_conflict="user_id",
        ).execute()

    # Entries (status defaults to 'completed'; embedded so vector retrieval works).
    entry_ids: list[str] = []
    for entry in fixtures.entries:
        text = entry["text"]
        embedding = await _embed_cached(text, EMBED_TASK)
        created_at = now - timedelta(days=int(entry.get("days_ago", 0)))
        row = supabase.table("entries").insert(
            {
                "raw_text": text,
                "cleaned_text": text,
                "auto_title": entry.get("title", ""),
                "summary": text,
                "user_id": user_id,
                "embedding": embedding,
                "created_at": created_at.isoformat(),
            }
        ).execute()
        entry_ids.append(row.data[0]["id"])

    # Deadlines — attach to the first seeded entry so list_deadlines' parent-entry
    # visibility filter is satisfied (parent must be completed + not soft-deleted).
    # Seeded for fidelity; the reliable content path for "list deadlines" is the
    # memory + the entry text (see scenarios.py SeedFixtures docstring).
    if fixtures.deadlines and entry_ids:
        parent = entry_ids[0]
        for d in fixtures.deadlines:
            supabase.table("deadlines").insert(
                {
                    "source_entry_id": parent,
                    "user_id": user_id,
                    "description": d["description"],
                    "due_date": d["due_date"],
                    "status": d.get("status", "pending"),
                }
            ).execute()

    # Entities (people/projects) — embedded, mirroring app/entity_resolver insert shape.
    for ent in fixtures.entities:
        description = f"{ent['name']} ({ent['type']})"
        embedding = await _embed_cached(description, EMBED_TASK)
        supabase.table("entities").insert(
            {
                "user_id": user_id,
                "name": ent["name"],
                "entity_type": ent["type"],
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "mention_count": 1,
                "embedding": embedding,
                "context_summary": "",
            }
        ).execute()


async def run_turns(user_id: str, turns: tuple[str, ...], now: datetime) -> list[dict]:
    """Drive the scripted USER turns through the LIVE pipeline, accumulating history
    exactly like ask_service.ask (generate first, then persist user+assistant)."""
    transcript: list[dict] = []
    for i, turn_text in enumerate(turns):
        # History is fetched inside generate_answer BEFORE we persist this turn,
        # so the current question is never in its own history — same as production.
        answer = await _with_backoff(
            lambda: generate_answer(turn_text, user_id), what=f"generation[t{i+1}]"
        )

        # Persist with strictly-increasing created_at so the desc-order history
        # fetch + loop detector see a deterministic order (prod ties on now()).
        ts_user = now + timedelta(seconds=2 * i)
        ts_asst = now + timedelta(seconds=2 * i + 1)
        supabase.table("ask_messages").insert(
            [
                {"user_id": user_id, "role": "user", "content": turn_text,
                 "created_at": ts_user.isoformat()},
                {"user_id": user_id, "role": "assistant", "content": answer,
                 "created_at": ts_asst.isoformat()},
            ]
        ).execute()

        transcript.append({"turn": i + 1, "role": "user", "content": turn_text})
        transcript.append({"turn": i + 1, "role": "assistant", "content": answer})
    return transcript


# ──────────────────────────────────────────────────────────────────────────────
# Per-case orchestration
# ──────────────────────────────────────────────────────────────────────────────
async def run_one(scenario, persona: str) -> dict:
    turns = get_turns(persona, scenario.id)
    now = datetime.now(timezone.utc)
    user_id = None
    base = {"scenario": scenario.id, "persona": persona,
            "probe_turn": _resolve_probe_turn(scenario, len(turns)),
            "property_kind": scenario.property_kind, "is_negative": scenario.is_negative}
    try:
        user_id = create_test_user()
        await seed_user(user_id, scenario.seed_fixtures, now)
        transcript = await run_turns(user_id, turns, now)
        verdict = await judge_case(scenario, persona, transcript)
        return {
            **base,
            "passed": verdict["passed"],
            "judge_reason": verdict["judge_reason"],
            "jaccard_overlap": verdict["jaccard_overlap"],
            "transcript": transcript,
            "test_user_id": user_id,
        }
    except SystemExit:
        raise  # judge-down: propagate the stop, don't swallow it
    except Exception as exc:
        return {
            **base,
            "passed": None,
            "judge_reason": None,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "transcript": locals().get("transcript", []),
            "test_user_id": user_id,
        }
    finally:
        if user_id:
            teardown_test_user(user_id)


# ──────────────────────────────────────────────────────────────────────────────
# Aggregation
# ──────────────────────────────────────────────────────────────────────────────
def _formal_redundancy_watch(results: list[dict]) -> dict:
    """Does `formal` ever fail a case `verbose_polite` passed? If never, flag it a
    candidate for collapse (per-persona observation, not a fix)."""
    by_key = {(r["scenario"], r["persona"]): r for r in results}
    unique_failures = []
    comparable = 0
    for scenario in SCENARIOS:
        f = by_key.get((scenario.id, "formal"))
        v = by_key.get((scenario.id, "verbose_polite"))
        if not f or not v or f.get("passed") is None or v.get("passed") is None:
            continue
        comparable += 1
        if f["passed"] is False and v["passed"] is True:
            unique_failures.append(scenario.id)
    return {
        "comparable_scenarios": comparable,
        "formal_unique_failures": unique_failures,
        "candidate_for_collapse": comparable > 0 and len(unique_failures) == 0,
        "note": FORMAL_REDUNDANCY_NOTE,
    }


def aggregate(results: list[dict]) -> dict:
    judged = [r for r in results if r.get("passed") is not None]
    errored = [r for r in results if r.get("passed") is None]
    passed = sum(1 for r in judged if r["passed"])

    per_persona: dict[str, dict] = {}
    per_scenario: dict[str, dict] = {}
    for r in judged:
        for bucket, key in ((per_persona, r["persona"]), (per_scenario, r["scenario"])):
            b = bucket.setdefault(key, {"passed": 0, "total": 0})
            b["total"] += 1
            if r["passed"]:
                b["passed"] += 1

    # The headline question: does the loop fix generalize, or only near the terse style?
    reask = {r["persona"]: r["passed"] for r in judged if r["scenario"] == "reask_loop"}

    return {
        "passed": passed,
        "total": len(judged),
        "errored": len(errored),
        "per_persona": per_persona,
        "per_scenario": per_scenario,
        "reask_loop_by_persona": reask,
        "formal_redundancy_watch": _formal_redundancy_watch(results),
    }


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(_ROOT)
        ).strip()
    except Exception:
        return "unknown"


def _print_report(summary: dict, results: list[dict]) -> None:
    print("\n" + "=" * 72)
    print(f"MULTI-TURN ASK EVAL — RED baseline  ({summary['passed']}/{summary['total']} passed)")
    print("=" * 72)

    print("\nPER-PERSONA")
    for persona, s in sorted(summary["per_persona"].items()):
        print(f"  {persona:<16} {s['passed']}/{s['total']}")
    print("\nPER-SCENARIO")
    for scen, s in sorted(summary["per_scenario"].items()):
        print(f"  {scen:<22} {s['passed']}/{s['total']}")

    print("\nHEADLINE — reask_loop pass by persona (does the loop fix generalize?)")
    for persona, ok in sorted(summary["reask_loop_by_persona"].items()):
        print(f"  {persona:<16} {'PASS' if ok else 'FAIL'}")

    frw = summary["formal_redundancy_watch"]
    print(
        f"\nFORMAL-REDUNDANCY WATCH: unique_failures={frw['formal_unique_failures']} "
        f"-> candidate_for_collapse={frw['candidate_for_collapse']}"
    )

    print("\nPER-CASE")
    for r in results:
        if r.get("passed") is None:
            print(f"  [ERROR] {r['scenario']:<22} {r['persona']:<16} {r.get('error')}")
        else:
            mark = "PASS" if r["passed"] else "FAIL"
            ov = f" ov={r['jaccard_overlap']}" if r.get("jaccard_overlap") is not None else ""
            print(f"  [{mark}] {r['scenario']:<22} {r['persona']:<16}{ov}  {r['judge_reason'][:90]}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
async def main(args: argparse.Namespace) -> None:
    print(f"[config] harness={HARNESS_NAME}  judge={JUDGE_MODEL_NAME}")
    print(f"[config] git HEAD={_git_sha()[:12]}")
    print(f"[scope] {SCOPE_CAVEAT}")

    # Judge gate — fail fast and LOUD if Pro is down; never fall back to string-match.
    await verify_judge()
    if args.verify_judge:
        print("[judge] --verify-judge only; exiting before any case runs.")
        return

    pairs = scenario_persona_pairs()
    if args.scenario:
        pairs = [(s, p) for (s, p) in pairs if s.id == args.scenario]
    if args.persona:
        pairs = [(s, p) for (s, p) in pairs if p == args.persona]
    if args.limit:
        pairs = pairs[: args.limit]
    print(f"[run] {len(pairs)} (scenario x persona) cases\n")

    results: list[dict] = []
    for idx, (scenario, persona) in enumerate(pairs, 1):
        print(f"[case {idx}/{len(pairs)}] {scenario.id} / {persona} ...", flush=True)
        res = await run_one(scenario, persona)
        if res.get("passed") is None:
            print(f"  -> ERROR: {res.get('error')}", flush=True)
        else:
            print(f"  -> {'PASS' if res['passed'] else 'FAIL'}: {res['judge_reason'][:100]}", flush=True)
        results.append(res)

    summary = aggregate(results)
    _print_report(summary, results)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sha = _git_sha()
    timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out_path = RESULTS_DIR / f"multiturn_{sha[:12]}_{timestamp}.json"
    payload: dict[str, Any] = {
        "commit_sha": sha,
        "timestamp": timestamp,
        "harness": HARNESS_NAME,
        "judge_model": JUDGE_MODEL_NAME,
        "personas_provenance": PERSONA_META.get("provenance_note"),
        "notes": {
            "formal_redundancy_watch": FORMAL_REDUNDANCY_NOTE,
            "scope_caveat": SCOPE_CAVEAT,
        },
        "summary": {"passed": summary["passed"], "total": summary["total"]},
        "breakdown": {
            "per_persona": summary["per_persona"],
            "per_scenario": summary["per_scenario"],
            "reask_loop_by_persona": summary["reask_loop_by_persona"],
            "errored": summary["errored"],
        },
        "formal_redundancy_watch": summary["formal_redundancy_watch"],
        "per_case": [
            {
                "scenario": r["scenario"],
                "persona": r["persona"],
                "probe_turn": r["probe_turn"],
                "property_kind": r.get("property_kind"),
                "is_negative": r.get("is_negative"),
                "passed": r.get("passed"),
                "judge_reason": r.get("judge_reason"),
                "jaccard_overlap": r.get("jaccard_overlap"),
                "error": r.get("error"),
                "transcript": r.get("transcript", []),
            }
            for r in results
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[results] {out_path}")


def _cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-turn Ask eval (persona x scenario, property-judged).")
    p.add_argument("--limit", type=int, default=0, help="Run only the first N cases.")
    p.add_argument("--scenario", type=str, default="", help="Restrict to one scenario id.")
    p.add_argument("--persona", type=str, default="", help="Restrict to one persona.")
    p.add_argument("--verify-judge", action="store_true", help="Probe the judge model and exit.")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_cli()))
