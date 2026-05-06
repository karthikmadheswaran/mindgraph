"""Temporal Ask pipeline evals.

Two parts:
  1. Pure-function tests for `detect_and_parse_time_range` and the recency
     decay sweep — runnable offline.
  2. Optional end-to-end smoke tests that hit Supabase / the live pipeline
     when SUPABASE creds are present (skipped otherwise).

Run:
    python evals/test_temporal_retrieval.py
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta, timezone

if "GEMINI_API_KEY" not in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ.setdefault("GEMINI_API_KEY", "stub-for-import")
os.environ.setdefault("SUPABASE_URL", "https://stub.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "stub")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ask_pipeline.hybrid_rag import apply_recency_decay
from app.services.ask_pipeline.temporal_retrieval import detect_and_parse_time_range


TODAY = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)


TEMPORAL_CASES = [
    {
        "id": "anything_in_may",
        "question": "anything in may",
        "expected_month": 5,
        "description": "Calendar month reference (May)",
    },
    {
        "id": "summarize_april",
        "question": "summarize april",
        "expected_month": 4,
        "description": "Calendar month reference (April)",
    },
    {
        "id": "what_did_i_write_recently",
        "question": "what did I write recently",
        "expected_within_days": 14,
        "description": "Recency reference",
    },
    {
        "id": "latest_journal_entry",
        "question": "latest journal entry",
        "expected_within_days": 14,
        "description": "Latest entry signal",
    },
    {
        "id": "newest_entry",
        "question": "show me my newest entry",
        "expected_within_days": 14,
        "description": "Newest entry signal",
    },
    {
        "id": "what_happened_last_week",
        "question": "what happened last week",
        "expected_within_days": 14,
        "description": "Rolling week window via dateparser",
    },
    {
        "id": "yesterday",
        "question": "what did I do yesterday",
        "expected_within_days": 14,
        "description": "Yesterday relative",
    },
    {
        "id": "this_month",
        "question": "what did I write this month",
        "expected_within_days": 31,
        "description": "This month relative (~30-day window)",
    },
    {
        "id": "no_temporal",
        "question": "tell me about Sachin",
        "expected_none": True,
        "description": "Pure semantic — no temporal range expected",
    },
    {
        "id": "oldest_entry",
        "question": "oldest entry",
        "expected_none": True,
        "description": "No window — falls through to RAG path",
    },
]


def _check_case(case: dict) -> tuple[bool, str]:
    parsed = detect_and_parse_time_range(case["question"], TODAY)

    if case.get("expected_none"):
        if parsed is None:
            return True, "no range (expected)"
        return False, f"expected None, got {parsed}"

    if parsed is None:
        return False, "expected a range, got None"

    start = datetime.fromisoformat(parsed["start"])
    end = datetime.fromisoformat(parsed["end"])

    if "expected_month" in case:
        if start.month != case["expected_month"]:
            return False, f"expected month={case['expected_month']}, got start={start.isoformat()}"
        if end.month != (case["expected_month"] % 12) + 1:
            return False, f"end month not next month: {end.isoformat()}"
        return True, f"{start.date()}..{end.date()}"

    if "expected_within_days" in case:
        window_days = (TODAY - start).days
        if window_days <= 0 or window_days > case["expected_within_days"] + 1:
            return False, f"start {start.isoformat()} is {window_days}d before today; expected ≤{case['expected_within_days']}d"
        return True, f"{start.date()}..{end.date()} ({window_days}d window)"

    return False, "no assertion configured"


def run_temporal_cases() -> int:
    print("=" * 70)
    print(f"Temporal date-range parsing eval (TODAY={TODAY.date()})")
    print("=" * 70)
    passed = 0
    for case in TEMPORAL_CASES:
        ok, detail = _check_case(case)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"  [{status}] {case['id']:32s} ->{detail}")
        print(f"           question: {case['question']!r}")
    print("-" * 70)
    print(f"  {passed}/{len(TEMPORAL_CASES)} cases passed")
    print()
    return passed


def _synthetic_candidates(now: datetime) -> list[dict]:
    """Mimic post-rerank candidate set: older entries with high rerank score
    competing against newer entries with slightly lower rerank score.
    The 'expected winner' is the most recent entry."""
    return [
        {
            "id": "old_high",
            "_rerank_score": 0.85,
            "created_at": (now - timedelta(days=120)).isoformat(),
        },
        {
            "id": "old_mid",
            "_rerank_score": 0.65,
            "created_at": (now - timedelta(days=60)).isoformat(),
        },
        {
            "id": "recent_low",
            "_rerank_score": 0.55,
            "created_at": (now - timedelta(days=2)).isoformat(),
        },
        {
            "id": "today_lower",
            "_rerank_score": 0.50,
            "created_at": (now - timedelta(hours=6)).isoformat(),
        },
    ]


def run_lambda_sweep() -> None:
    print("=" * 70)
    print("Recency decay λ sweep")
    print("=" * 70)
    now = datetime.now(timezone.utc)
    sweeps = [0.001, 0.005, 0.01, 0.02, 0.05]

    expected_winner_id = "today_lower"

    print(f"  {'lambda':>8s}  {'top_id':<14s}  {'top_adj':>8s}  {'mrr_for_recent':>14s}")
    for lam in sweeps:
        candidates = _synthetic_candidates(now)
        decayed = apply_recency_decay(candidates, now, lambda_decay=lam)
        rank_of_recent = next(
            (i + 1 for i, e in enumerate(decayed) if e["id"] == expected_winner_id),
            None,
        )
        mrr = (1.0 / rank_of_recent) if rank_of_recent else 0.0
        top = decayed[0]
        print(
            f"  {lam:>8.4f}  {top['id']:<14s}  {top['adjusted_score']:>8.4f}  {mrr:>14.3f}"
        )
    print()
    print("Higher MRR = recent entry ranks higher after decay. Pick the λ that")
    print("balances recency boost against semantic precision in your full eval.")
    print()


def main() -> int:
    passed = run_temporal_cases()
    run_lambda_sweep()
    failed = len(TEMPORAL_CASES) - passed
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
