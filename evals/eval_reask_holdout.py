"""
evals/eval_reask_holdout.py — Hold-out check for query-agent re-ask detection.

WHAT THIS IS
------------
The multi-turn harness (eval_ask_multiturn) exercises is_reask through five
FROZEN persona phrasings of the reask_loop scenario. A detector that merely
memorizes those phrasings would pass the harness and still fail real users, so
this hold-out runs FRESH phrasings (absent from evals/multiturn/personas.py,
varied register: terse / apologetic / irritated / rambling / indirect) plus
three genuine follow-ups that must NOT be flagged.

It is a direct query-agent unit run: the same _build_prompt + structured
RoutingDecision call the pipeline makes, with a synthetic deadline conversation
as history. No Supabase user, no retrieval, no generation — the unit under test
is the semantic re-ask judgment alone.

USAGE
-----
    python -m evals.eval_reask_holdout

Exit code 0 only if all 8 cases produce the expected is_reask value. Results go
to evals/results/reask_holdout_<sha>_<ts>.json (SHA-stamped, committed).
"""

from __future__ import annotations

import asyncio
import codecs
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv(encoding="utf-8-sig")

if not os.getenv("GEMINI_API_KEY"):
    _env_path = _ROOT / ".env"
    if _env_path.exists():
        for line in codecs.open(_env_path, "r", "utf-8-sig").read().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip()
                break
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

from app.ask_memory import extract_prior_user_messages  # noqa: E402
from app.services.ask_pipeline.query_agent import (  # noqa: E402
    _REASK_HISTORY_TURNS,
    _build_prompt,
    _structured_flash,
)

RESULTS_DIR = _HERE / "results"

# Shared synthetic conversation: the user already asked for their deadlines and
# the assistant already answered. Every case below is the NEXT user turn.
_HISTORY = (
    "User: what deadlines do I have coming up?\n"
    "Assistant: You have three deadlines coming up: getting a job by May 31, "
    "Sachin's wedding on May 31, and the Razorpay merchant application due May 28."
)

# Hold-out fixtures. Phrasings verified absent from evals/multiturn/personas.py
# (the harness's frozen reask_loop turns) — that absence is the point.
CASES: tuple[dict, ...] = (
    # -- 5 fresh re-asks (expected is_reask=True) ----------------------------
    {"id": "terse_reask", "register": "terse",
     "question": "what's due again?", "expected": True},
    {"id": "apologetic_reask", "register": "apologetic",
     "question": ("so sorry — I completely forgot what you just told me. could "
                  "you run through what I have coming up one more time?"),
     "expected": True},
    {"id": "irritated_reask", "register": "irritated",
     "question": "you're not listening. tell me what i have due. one. more. time.",
     "expected": True},
    {"id": "rambling_reask", "register": "rambling",
     "question": ("ok so i got distracted by like five other things and now i "
                  "genuinely cannot remember a single thing from that list you "
                  "gave me, something about a wedding? idk, can you go over "
                  "everything i have coming up?"),
     "expected": True},
    {"id": "indirect_reask", "register": "indirect",
     "question": ("i keep losing track of what's on my plate. walk me through "
                  "my upcoming deadlines."),
     "expected": True},
    # -- 3 genuine follow-ups (expected is_reask=False) ----------------------
    {"id": "followup_which_first", "register": "follow-up (narrow)",
     "question": "which one is due first?", "expected": False},
    {"id": "followup_add_item", "register": "follow-up (extend)",
     "question": "can you add the dentist appointment to that list?",
     "expected": False},
    {"id": "followup_why_late", "register": "follow-up (probe)",
     "question": "why is the Razorpay one late?", "expected": False},
)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(_ROOT)
        ).strip()
    except Exception:
        return "unknown"


async def run_case(case: dict) -> dict:
    prior_user_turns = extract_prior_user_messages(_HISTORY)[-_REASK_HISTORY_TURNS:]
    prompt = _build_prompt(
        question=case["question"],
        today="2026-06-11",
        entity_list="- Sachin (person, 2 mentions)\n- Razorpay (organization, 1 mentions)",
        recent="(no recent entries)",
        prior_user_turns=prior_user_turns,
    )
    # Eval-infra resilience only: Vertex occasionally returns an empty response
    # that parses to None (production falls back to default routing on the same
    # failure), and local network blips surface as 503s. Retry a few times so a
    # transient doesn't fail the hold-out; if it persists, surface it for real.
    result = None
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            # wait_for guards against hangs (observed: gRPC channel wedge on a
            # network flap, and the pre-tb=0 thinking spiral at ~350s). 180s is
            # loose enough for tenacity's in-client 429 backoff to complete.
            result = await asyncio.wait_for(
                _structured_flash.ainvoke(prompt), timeout=180
            )
        except Exception as exc:  # noqa: BLE001 — eval infra, retry transients
            last_exc = exc
            print(f"  [retry] {case['id']} attempt {attempt + 1}: {type(exc).__name__}: {str(exc)[:120]}")
            result = None
        if result is not None:
            break
        # Long sleeps on purpose: the project's per-minute Vertex quota needs a
        # fresh window (same reason eval_ask_multiturn._with_backoff exists).
        await asyncio.sleep(min(90, 30 * (attempt + 1)))
    if result is None:
        # Don't abort the whole run for one stuck case — record it as a failure
        # (got=None distinguishes "never answered" from a wrong boolean).
        return {
            **{k: case[k] for k in ("id", "register", "question", "expected")},
            "got": None,
            "passed": False,
            "error": f"{type(last_exc).__name__}: {str(last_exc)[:200]}" if last_exc else "empty response",
        }
    got = bool(result.is_reask)
    return {
        **{k: case[k] for k in ("id", "register", "question", "expected")},
        "got": got,
        "passed": got == case["expected"],
    }


async def main() -> None:
    sha = _git_sha()
    print(f"[config] reask hold-out — git HEAD={sha[:12]}, {len(CASES)} cases\n")

    results = []
    for i, c in enumerate(CASES):
        if i:
            # Pace cases so 8 back-to-back ~1K-token prompts don't exhaust the
            # project's per-minute Vertex quota mid-run.
            await asyncio.sleep(15)
        r = await run_case(c)
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['id']:<22} expected={r['expected']!s:<5} got={r['got']!s:<5} ({r['register']})", flush=True)
        results.append(r)
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} hold-out cases passed")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out_path = RESULTS_DIR / f"reask_holdout_{sha[:12]}_{timestamp}.json"
    out_path.write_text(
        json.dumps(
            {
                "commit_sha": sha,
                "timestamp": timestamp,
                "harness": "reask_holdout",
                "summary": {"passed": passed, "total": len(results)},
                "per_case": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[results] {out_path}")

    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
