# rag_evaluation.py
"""
RAG Evaluation for MindGraph Journal App

Measures three things:
1. Retrieval Accuracy - Did we find the right entries?
2. Answer Quality - Did the LLM answer correctly without hallucinating?
3. Latency - How fast is the live Ask pipeline?

Usage: python evals/rag_evaluation.py

────────────────────────────────────────────────────────────────────────────
PRODUCTION ENTRY POINT (verified by reading the code on 2026-06-05, not assumed)
────────────────────────────────────────────────────────────────────────────
  POST /ask                       app/main.py:159        ask_question
    -> ask_service.ask            app/services/ask_service.py:630
      -> ask_service.generate_answer
                                  app/services/ask_service.py:494
        -> ask_pipeline.ainvoke(initial_state)
                                  app/services/ask_service.py:570

`ask_pipeline` is the compiled LangGraph DAG built in
app/services/ask_pipeline/graph.py:

    query_understanding_agent  ->  router (fan-out)  ->  4 parallel branches
        [ temporal_retrieval, recent_summaries, hybrid_rag, dashboard_context ]
    ->  context_assembler  ->  generation

`ainvoke` returns the final AskState dict. The fields this eval scores against:
  query_types          - router classification, e.g. ["temporal"]
  temporal_entries     - entries from the date-range branch (temporal_retrieval)
  rag_entries          - entries from hybrid_rag (BM25 + pgvector + Cohere rerank
                         + recency decay)
  recent_summaries     - always-on last-5 baseline (NOT counted as a retrieval
                         hit, mirroring context_assembler's corroboration rule)
  rag_max_similarity   - top cosine; the hybrid_rag confidence signal
  temporal_has_results / dashboard_has_results - per-branch corroboration flags
  is_low_confidence    - context_assembler's refusal gate (HIGH_CONFIDENCE_THRESHOLD
                         corroborated by the temporal/dashboard branches). This is
                         the exact decision behind the live "I don't see anything
                         about that in your journal entries" refusal.
  answer               - the production-generated answer (generation node, flash)

Because this eval invokes that same compiled graph, every threshold
(MIN_SIMILARITY, HIGH_CONFIDENCE_THRESHOLD), the deleted_at IS NULL / status =
'completed' filters, recency decay, Cohere rerank, and the refusal gate are all
applied by PRODUCTION code — none of it is re-implemented here. Temporal queries
now flow through temporal_retrieval via the router instead of a direct
match_entries vector search, closing the 26-May-style divergence where the
harness scored a different path than production (the MIN_SIMILARITY gap).
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Make the repo root importable when run as a script (python evals/rag_evaluation.py):
# Python puts the script's own dir on sys.path, not the repo root, so `app` would
# otherwise be unimportable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load env BEFORE importing any app.* module: app.llm constructs the Gemini
# client at import time and reads GOOGLE_API_KEY. utf-8-sig tolerates the local
# .env UTF-8 BOM (tracked separately as a P3 Known-Broken item) so the harness
# runs locally; production reads the same vars from the Railway environment.
load_dotenv(encoding="utf-8-sig")
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

from app.services.ask_pipeline import AskState, ask_pipeline  # noqa: E402
from app.services.ask_pipeline.context_assembler import (  # noqa: E402
    EFFECTIVE_HIGH_CONFIDENCE,
)
from app.services.ask_service import (  # noqa: E402
    HIGH_CONFIDENCE_THRESHOLD,
    MIN_SIMILARITY,
    resolve_user_timezone,
)

USER_ID = "97372247-26b1-42a1-9e54-76d6dfe55346"

# Test cases live in evals/rag_test_cases.json, generated against the current
# test user's actual entries via evals/generate_rag_test_cases.py. Scoring keys
# off expected_entry_id (stable) rather than title substrings (fragile).
_test_cases_path = Path(__file__).resolve().parent / "rag_test_cases.json"
with open(_test_cases_path, encoding="utf-8") as _f:
    _payload = json.load(_f)
TEST_CASES = _payload["cases"]
assert _payload["test_user_id"] == USER_ID, (
    f"rag_test_cases.json was generated for {_payload['test_user_id']} but eval is "
    f"configured for {USER_ID}. Regenerate with evals/generate_rag_test_cases.py."
)


def _build_initial_state(question: str, user_tz: str) -> AskState:
    """Mirror app/services/ask_service.generate_answer's initial_state exactly.

    conversation_history / long_term_memory are empty: each eval case is a cold,
    single-turn question with no prior session, which is the cleanest signal for
    retrieval and matches the first /ask in a fresh session. Every other field is
    seeded identically to production so the graph nodes behave the same.
    """
    return {
        "question": question,
        "user_id": USER_ID,
        "conversation_history": "",
        "long_term_memory": "",
        "user_timezone": user_tz,
        "query_types": [],
        "time_range": None,
        "entities_mentioned": [],
        "dashboard_context_needed": False,
        "today_str": "",
        "temporal_entries": [],
        "recent_summaries": [],
        "rag_entries": [],
        "dashboard_context": {},
        "rag_max_similarity": 0.0,
        "temporal_has_results": False,
        "dashboard_has_results": False,
        "is_low_confidence": False,
        "is_reask": False,
        "assembled_context": "",
        "answer": "",
    }


async def run_pipeline(question: str, user_tz: str) -> tuple[dict, int]:
    """Invoke the live Ask pipeline (same graph /ask uses) for one question."""
    state = _build_initial_state(question, user_tz)
    start = time.time()
    final_state = await ask_pipeline.ainvoke(state)
    elapsed_ms = round((time.time() - start) * 1000)
    return final_state, elapsed_ms


def _ids(entries: list | None) -> list[str]:
    return [e.get("id", "") for e in (entries or []) if e.get("id")]


def score_retrieval(
    final_state: dict,
    expected_entry_id: str | None,
    category: str,
) -> dict:
    """Score retrieval off the final AskState the live pipeline produced.

    Non-null cases: hit iff expected_entry_id appears in the query-driven
    retrieval set (temporal_retrieval ∪ hybrid_rag). recent_summaries is excluded
    from the hit set — it's the always-on last-5 baseline (the same reason
    context_assembler excludes it from confidence corroboration), so a
    coincidental recent entry cannot be scored as a retrieval hit.

    Null cases (hard_null): hit iff the live refusal gate fires
    (is_low_confidence). This is the SAME gate the /ask path uses to emit
    "I don't see anything about that in your journal entries", replacing the old
    vector-only `top_sim < MIN_SIMILARITY` heuristic with the real production
    decision.

    Since each case has exactly one correct answer (or zero, for null cases),
    precision == recall == F1 per case; the averaged F1 is the hit rate.
    """
    query_types = final_state.get("query_types") or []
    temporal_ids = _ids(final_state.get("temporal_entries"))
    rag_ids = _ids(final_state.get("rag_entries"))
    recent_ids = _ids(final_state.get("recent_summaries"))
    retrieved_ids = list(dict.fromkeys(temporal_ids + rag_ids))

    is_low_confidence = bool(final_state.get("is_low_confidence"))
    routed_temporal = "temporal" in query_types

    if category == "hard_null":
        hit = is_low_confidence
        rank = 0
    else:
        hit = bool(expected_entry_id) and expected_entry_id in retrieved_ids
        rank = retrieved_ids.index(expected_entry_id) + 1 if hit else 0

    score = 1.0 if hit else 0.0
    expected_in_temporal_branch = (
        bool(expected_entry_id) and expected_entry_id in temporal_ids
    )

    return {
        "category": category,
        "query_types": query_types,
        "routed_temporal": routed_temporal,
        "retrieved_ids": retrieved_ids,
        "temporal_entry_ids": temporal_ids,
        "rag_entry_ids": rag_ids,
        "recent_entry_ids": recent_ids,
        "expected_entry_id": expected_entry_id,
        "expected_in_temporal_branch": expected_in_temporal_branch,
        "is_low_confidence": is_low_confidence,
        "rag_max_similarity": round(float(final_state.get("rag_max_similarity") or 0.0), 3),
        "temporal_has_results": bool(final_state.get("temporal_has_results")),
        "dashboard_has_results": bool(final_state.get("dashboard_has_results")),
        "hit": hit,
        "rank": rank,
        "precision": score,
        "recall": score,
        "f1_score": score,
    }


def score_answer(
    final_state: dict,
    expected_keywords: list[str],
    forbidden_keywords: list[str] | None = None,
) -> dict:
    """Score the PRODUCTION-generated answer (generation node output).

    No separate LLM call and no separate prompt — we read state["answer"], the
    exact text /ask would return, so answer quality reflects production's prompt
    (v13.x), model (flash), and the is_low_confidence refusal behavior.
    """
    forbidden_keywords = forbidden_keywords or []
    answer = final_state.get("answer") or ""
    answer_lower = answer.lower()

    keywords_found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    keywords_missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
    hallucinations = [kw for kw in forbidden_keywords if kw.lower() in answer_lower]

    keyword_score = (
        len(keywords_found) / len(expected_keywords) if expected_keywords else 1.0
    )
    hallucination_score = (
        1.0 - (len(hallucinations) / len(forbidden_keywords))
        if forbidden_keywords
        else 1.0
    )

    return {
        "answer": answer[:200] + "..." if len(answer) > 200 else answer,
        "keywords_found": keywords_found,
        "keywords_missing": keywords_missing,
        "hallucinations": hallucinations,
        "keyword_score": round(keyword_score, 3),
        "hallucination_score": round(hallucination_score, 3),
    }


async def run_evaluation():
    """Run full RAG evaluation through the live Ask pipeline."""
    print("=" * 70)
    print("🧪 MindGraph RAG Evaluation — via live Ask pipeline (ask_pipeline)")
    print("=" * 70)

    # Resolve the test user's timezone exactly as /ask does for a request with
    # no browser timezone — this matters for temporal date-range boundaries (IST).
    user_tz = await resolve_user_timezone(USER_ID, None)

    print(f"Test cases:               {len(TEST_CASES)}")
    print(f"User timezone:            {user_tz}")
    print(f"MIN_SIMILARITY:           {MIN_SIMILARITY}")
    print(f"HIGH_CONFIDENCE_THRESHOLD:{HIGH_CONFIDENCE_THRESHOLD} "
          f"(effective={EFFECTIVE_HIGH_CONFIDENCE})")
    print()

    results = []
    total_pipeline_time = 0
    total_f1 = 0
    total_keyword_score = 0
    total_hallucination_score = 0

    # Step 5 — temporal routing proof. We do NOT assume the router classified
    # temporal cases correctly; we record it per case and surface failures.
    routing_misclassified = []   # temporal case the router did NOT mark temporal
    temporal_branch_misses = []  # routed temporal but expected entry not in branch

    for i, test in enumerate(TEST_CASES, 1):
        category = test.get("category", "uncategorised")
        print(f"─── Test {i}/{len(TEST_CASES)} [{category}]: {test['question']}")

        final_state, elapsed_ms = await run_pipeline(test["question"], user_tz)

        retrieval = score_retrieval(
            final_state,
            test.get("expected_entry_id"),
            category,
        )
        answer_eval = score_answer(
            final_state,
            test.get("expected_keywords", []),
            test.get("forbidden_keywords"),
        )

        rank_str = f"rank={retrieval['rank']}" if retrieval["rank"] else "miss"
        print(
            f"  Routing:   query_types={retrieval['query_types']} | "
            f"low_conf={retrieval['is_low_confidence']} | "
            f"rag_max_sim={retrieval['rag_max_similarity']}"
        )
        print(
            f"  Retrieval: hit={retrieval['hit']} ({rank_str}) | "
            f"temporal_branch={len(retrieval['temporal_entry_ids'])} entries, "
            f"rag_branch={len(retrieval['rag_entry_ids'])} entries | {elapsed_ms}ms"
        )
        print(
            f"  Answer:    Keywords={answer_eval['keyword_score']} | "
            f"Hallucination={answer_eval['hallucination_score']}"
        )
        if answer_eval["keywords_missing"]:
            print(f"  ⚠ Missing:  {answer_eval['keywords_missing']}")
        if answer_eval["hallucinations"]:
            print(f"  ❌ Hallucinated: {answer_eval['hallucinations']}")

        # Step 5 — explicit assertion + proof line for every temporal case:
        # prove the router classified it temporal AND sent it down the
        # date-range branch (temporal_retrieval), not the vector path.
        if category == "temporal":
            print(
                "  ↳ TEMPORAL ROUTING PROOF: "
                f"routed_temporal={retrieval['routed_temporal']} "
                f"temporal_branch_entries={len(retrieval['temporal_entry_ids'])} "
                f"expected_in_temporal_branch={retrieval['expected_in_temporal_branch']}"
            )
            try:
                assert retrieval["routed_temporal"], (
                    "router did NOT classify a temporal case as temporal "
                    f"(query_types={retrieval['query_types']})"
                )
            except AssertionError as exc:
                routing_misclassified.append((test["question"], str(exc)))
                print(f"  ‼ ROUTER MISCLASSIFICATION: {exc}")
            if retrieval["routed_temporal"] and not retrieval["expected_in_temporal_branch"]:
                temporal_branch_misses.append(test["question"])
        print()

        total_pipeline_time += elapsed_ms
        total_f1 += retrieval["f1_score"]
        total_keyword_score += answer_eval["keyword_score"]
        total_hallucination_score += answer_eval["hallucination_score"]

        results.append(
            {
                "question": test["question"],
                "retrieval": retrieval,
                "answer": answer_eval,
                "pipeline_time_ms": elapsed_ms,
            }
        )

    # Summary
    n = len(TEST_CASES)
    print("=" * 70)
    print("📊 EVALUATION SUMMARY")
    print("=" * 70)
    print(f"  Total test cases:         {n}")
    print(f"  Avg Retrieval F1:         {round(total_f1 / n, 3)}")
    print(f"  Avg Keyword Score:        {round(total_keyword_score / n, 3)}")
    print(f"  Avg Hallucination Score:  {round(total_hallucination_score / n, 3)}")
    print(f"  Avg Pipeline Latency:     {round(total_pipeline_time / n)}ms")
    print(f"  Total Evaluation Time:    {round(total_pipeline_time / 1000, 1)}s")
    print("=" * 70)

    # MRR over non-null cases; per-category hit rate.
    mrr_total = 0.0
    mrr_n = 0
    pass_count = 0
    category_stats: dict = {}
    for r in results:
        cat = r["retrieval"]["category"]
        category_stats.setdefault(cat, {"n": 0, "hits": 0})
        category_stats[cat]["n"] += 1
        if r["retrieval"]["hit"]:
            category_stats[cat]["hits"] += 1
            pass_count += 1
        if cat != "hard_null":
            rank = r["retrieval"]["rank"]
            mrr_total += (1.0 / rank) if rank else 0.0
            mrr_n += 1
    mrr = round(mrr_total / mrr_n, 3) if mrr_n else 0.0
    pass_rate = round(pass_count / n, 3) if n else 0.0
    wall_clock_s = round(total_pipeline_time / 1000, 1)

    print("\n  Hit rate by category:")
    for cat in sorted(category_stats):
        cs = category_stats[cat]
        rate = round(cs["hits"] / cs["n"], 3) if cs["n"] else 0.0
        print(f"    {cat:14}: {cs['hits']}/{cs['n']} = {rate}")

    temporal_stats = category_stats.get("temporal", {"n": 0, "hits": 0})
    temporal_f1 = (
        round(temporal_stats["hits"] / temporal_stats["n"], 3)
        if temporal_stats["n"]
        else 0.0
    )

    print(f"  MRR:                      {mrr}")
    print(f"  Pass rate (F1>0):         {pass_rate}")
    print(f"  Wall-clock:               {wall_clock_s}s")
    print("=" * 70)

    # ── Step 5: TEMPORAL ROUTING REPORT ──────────────────────────────────────
    # This is the whole point of the reroute: the harness must catch router
    # misclassification, not assume correct routing.
    temporal_cases = [r for r in results if r["retrieval"]["category"] == "temporal"]
    routed_ok = sum(1 for r in temporal_cases if r["retrieval"]["routed_temporal"])
    in_branch = sum(
        1 for r in temporal_cases if r["retrieval"]["expected_in_temporal_branch"]
    )
    print("\n  TEMPORAL ROUTING REPORT (Step 5):")
    print(f"    temporal cases:                 {len(temporal_cases)}")
    print(f"    classified temporal by router:  {routed_ok}/{len(temporal_cases)}")
    print(f"    expected entry surfaced by the temporal branch: "
          f"{in_branch}/{len(temporal_cases)}")
    print(f"    temporal F1 (real date-range branch): {temporal_f1}")
    if routing_misclassified:
        print("    ‼ ROUTER MISCLASSIFICATIONS:")
        for q, why in routing_misclassified:
            print(f"      - {q}  ({why})")
    else:
        print("    ✅ every temporal case was routed to temporal_retrieval")
    if temporal_branch_misses:
        print("    ⚠ temporal-branch misses (routed temporal, expected entry not in branch):")
        for q in temporal_branch_misses:
            print(f"      - {q}")
    print("=" * 70)

    summary = {
        "test_cases": n,
        "user_id": USER_ID,
        "user_timezone": user_tz,
        "entry_point": "ask_pipeline.ainvoke (live /ask path)",
        "min_similarity": MIN_SIMILARITY,
        "high_confidence_threshold": HIGH_CONFIDENCE_THRESHOLD,
        "effective_high_confidence": EFFECTIVE_HIGH_CONFIDENCE,
        "avg_retrieval_f1": round(total_f1 / n, 3),
        "temporal_f1": temporal_f1,
        "mrr": mrr,
        "mrr_scope": "non-null cases only",
        "pass_rate": pass_rate,
        "category_hit_rate": {
            cat: round(cs["hits"] / cs["n"], 3) if cs["n"] else 0.0
            for cat, cs in category_stats.items()
        },
        "temporal_routing": {
            "temporal_cases": len(temporal_cases),
            "classified_temporal": routed_ok,
            "expected_in_temporal_branch": in_branch,
            "router_misclassified": [q for q, _ in routing_misclassified],
            "temporal_branch_misses": temporal_branch_misses,
        },
        "avg_keyword_score": round(total_keyword_score / n, 3),
        "avg_hallucination_score": round(total_hallucination_score / n, 3),
        "avg_pipeline_latency_ms": round(total_pipeline_time / n),
        "wall_clock_seconds": wall_clock_s,
    }
    with open("rag_evaluation_results.json", "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, default=str)

    label = os.getenv("RAG_EVAL_LABEL", "run")
    timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    tagged_path = results_dir / f"rag_eval_{label}_{timestamp}.json"
    with open(tagged_path, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, default=str)

    print(f"\n📁 Detailed results saved to rag_evaluation_results.json")
    print(f"📁 Tagged copy:           {tagged_path}")


if __name__ == "__main__":
    asyncio.run(run_evaluation())


# ─────────────────────────────────────────────────────────────────────────────
# OLD TEST_CASES — preserved for revert
# ─────────────────────────────────────────────────────────────────────────────
# Replaced 2026-05-26. The previous test set referenced ~15 entry titles like
# "Had coffee with Sneha" / "Quitting Job for New Ventures" that no longer
# exist in any current production user's DB (USER_ID e5e611e2-... only has 4
# active entries). Every case scored F1=0 so the eval was non-measuring.
#
# Replaced with auto-generated cases grounded in test user
# 97372247-26b1-42a1-9e54-76d6dfe55346 — see evals/generate_rag_test_cases.py
# and evals/rag_test_cases.json. New scoring keys off expected_entry_id
# (stable) rather than title substrings (fragile).
#
# Kept as a docstring rather than commented lines so it survives reformatters.
_OLD_TEST_CASES_PRESERVED = """
[
    {"question": "What have I been working on with Sneha?",
     "expected_titles": ["Debugging and Startup Ideas", "Debugging Success and Feeling Homesick", "Had coffee with Sneha"],
     "expected_keywords": ["auth", "debug", "Sneha"], "forbidden_keywords": []},
    {"question": "What are my health issues recently?",
     "expected_titles": ["Struggling Through a Migraine Day", "Cosmic Perspective and Life Logistics"],
     "expected_keywords": ["migraine", "medicine"], "forbidden_keywords": []},
    {"question": "Tell me about my family and parents",
     "expected_titles": ["Planning Parents' Bangalore Visit", "Upcoming Deadlines and Family Calls"],
     "expected_keywords": ["mom", "dad", "Bangalore"], "forbidden_keywords": []},
    {"question": "What startup ideas have I discussed?",
     "expected_titles": ["Startup Strategy with Arun", "Debugging and Startup Ideas"],
     "expected_keywords": ["Arun", "startup"], "forbidden_keywords": []},
    {"question": "How much money have I been spending?",
     "expected_titles": ["Productive Day Amidst Financial Stress", "Struggling Through a Migraine Day", "Cosmic Perspective and Life Logistics", "Amazing Brigade Road Coffee Discovery"],
     "expected_keywords": ["spent", "medicine"], "forbidden_keywords": []},
    {"question": "What happened when I quit my job?",
     "expected_titles": ["Quitting Job for New Ventures"],
     "expected_keywords": ["quit", "exciting", "scary"], "forbidden_keywords": []},
    {"question": "What places have I visited in Bangalore?",
     "expected_titles": ["Debugging Success and Feeling Homesick", "Amazing Brigade Road Coffee Discovery", "Cosmic Perspective and Life Logistics"],
     "expected_keywords": ["Bangalore"], "forbidden_keywords": []},
    {"question": "What bugs have I been fixing?",
     "expected_titles": ["Addressing Auth Module Issues", "Fixing Session Timeout Bug", "Debugging Success and Feeling Homesick"],
     "expected_keywords": ["auth", "bug"], "forbidden_keywords": []},
    {"question": "How has my mood been lately?",
     "expected_titles": ["Quitting Job for New Ventures", "Struggling Through a Migraine Day", "Debugging Success and Feeling Homesick"],
     "expected_keywords": [], "forbidden_keywords": []},
    {"question": "What deadlines do I have coming up?",
     "expected_titles": ["Upcoming Deadlines and Family Calls", "Pitch Deck Prep and Nerves"],
     "expected_keywords": [], "forbidden_keywords": []},
    {"question": "Who is Arun and what have we discussed?",
     "expected_titles": ["Startup Strategy with Arun"],
     "expected_keywords": ["Arun", "startup"], "forbidden_keywords": []},
    {"question": "What did I do about the MindGraph deployment?",
     "expected_titles": ["MindGraph Deployment Success in Bangalore", "Deployment Progress and Security Lessons"],
     "expected_keywords": ["deploy", "Railway"], "forbidden_keywords": []},
    {"question": "Have I been exercising recently?",
     "expected_titles": ["Debugging Success and Feeling Homesick", "Cosmic Perspective and Life Logistics"],
     "expected_keywords": ["run", "gym"], "forbidden_keywords": []},
    {"question": "What coffee experiences have I had?",
     "expected_titles": ["Amazing Brigade Road Coffee Discovery", "Debugging and Startup Ideas", "Had coffee with Sneha"],
     "expected_keywords": ["coffee"], "forbidden_keywords": []},
    {"question": "What have I been feeling homesick about?",
     "expected_titles": ["Debugging Success and Feeling Homesick"],
     "expected_keywords": ["home", "missing"], "forbidden_keywords": []},
]
"""
