# rag_evaluation.py
"""
RAG Evaluation for MindGraph Journal App

Measures three things:
1. Retrieval Accuracy - Did we find the right entries?
2. Answer Quality - Did the LLM answer correctly without hallucinating?
3. Latency - How fast is retrieval + generation?

Usage: python rag_evaluation.py
"""

import asyncio
import time
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from app.embeddings import get_embedding
from app.nodes.store import supabase
from app.services.ask_service import MIN_SIMILARITY
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.1)

USER_ID = "97372247-26b1-42a1-9e54-76d6dfe55346"

# Null-case correctness threshold: defaults to MIN_SIMILARITY in
# app/services/ask_service.py (the live filter), overridable via env var for
# threshold sweeps. If retrieval's top similarity is below this, the live system
# would filter the result out, so a null-case is "correct" iff no row clears the
# bar.
_MIN_SIMILARITY_OVERRIDE = os.environ.get("RAG_EVAL_MIN_SIMILARITY")
NULL_CASE_SIM_THRESHOLD = (
    float(_MIN_SIMILARITY_OVERRIDE) if _MIN_SIMILARITY_OVERRIDE else MIN_SIMILARITY
)

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

# Old TEST_CASES (May 2025 era) live as a comment block at the very bottom of
# this file under the heading "OLD TEST_CASES — preserved for revert". They
# scored F1=0 across every case because none of the referenced entry titles
# existed in any current production user, which is why we regenerated.


def extract_text_from_response(response):
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()


async def evaluate_retrieval(
    question: str,
    expected_entry_id: str | None,
    category: str,
) -> dict:
    """
    Evaluate retrieval against a single expected entry ID.

    Non-null cases: hit iff expected_entry_id appears in top-K retrieved IDs.
    Null cases (hard_null): hit iff the live system WOULDN'T return the top
    match (top similarity < NULL_CASE_SIM_THRESHOLD).

    Since each case has exactly one correct answer (or zero, for null cases),
    precision == recall == F1 — all binary per case. The averaged F1 is
    effectively the hit rate across the test set.
    """
    start = time.time()

    query_embedding = await get_embedding(question, task_type="RETRIEVAL_QUERY")

    result = supabase.rpc("match_entries", {
        "query_embedding": query_embedding,
        "match_count": 5,
        "filter_user_id": USER_ID
    }).execute()

    retrieval_time = time.time() - start
    data = result.data or []

    retrieved_ids = [r.get("id", "") for r in data]
    retrieved_titles = [r.get("auto_title", "") for r in data]
    similarities = [round(r.get("similarity", 0) or 0, 3) for r in data]

    if category == "hard_null":
        top_sim = max(similarities) if similarities else 0.0
        hit = top_sim < NULL_CASE_SIM_THRESHOLD
        rank = 0
    else:
        hit = bool(expected_entry_id) and expected_entry_id in retrieved_ids
        rank = retrieved_ids.index(expected_entry_id) + 1 if hit else 0

    score = 1.0 if hit else 0.0

    return {
        "retrieved_ids": retrieved_ids,
        "retrieved_titles": retrieved_titles,
        "expected_entry_id": expected_entry_id,
        "category": category,
        "hit": hit,
        "rank": rank,
        "precision": score,
        "recall": score,
        "f1_score": score,
        "retrieval_time_ms": round(retrieval_time * 1000),
        "similarities": similarities,
    }


async def evaluate_answer(question: str, retrieved_entries: list, expected_keywords: list[str], forbidden_keywords: list[str] | None = None) -> dict:
    forbidden_keywords = forbidden_keywords or []
    """Evaluate the quality of the generated answer"""
    start = time.time()
    
    formatted_entries = []
    for i, entry in enumerate(retrieved_entries, 1):
        date = entry.get("created_at", "Unknown")
        title = entry.get("auto_title", "Untitled")
        formatted_entries.append(f"Entry {i} ({date}, {title}):\n{entry['cleaned_text']}")
    
    context = "\n\n---\n\n".join(formatted_entries)
    
    prompt = f"""You are an assistant for a personal journal app. A user has asked:
    "{question}"

    Relevant journal entries:
    {context}
    
    Based on these entries, provide a helpful answer. If the entries don't contain relevant info, say "I don't know"."""
    
    response = await model.ainvoke(prompt)
    answer = extract_text_from_response(response)
    
    generation_time = time.time() - start
    
    # Check expected keywords
    answer_lower = answer.lower()
    keywords_found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    keywords_missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
    
    # Check forbidden keywords (hallucination)
    hallucinations = [kw for kw in forbidden_keywords if kw.lower() in answer_lower]
    
    keyword_score = len(keywords_found) / len(expected_keywords) if expected_keywords else 1.0
    hallucination_score = 1.0 - (len(hallucinations) / len(forbidden_keywords)) if forbidden_keywords else 1.0
    
    return {
        "answer": answer[:200] + "..." if len(answer) > 200 else answer,
        "keywords_found": keywords_found,
        "keywords_missing": keywords_missing,
        "hallucinations": hallucinations,
        "keyword_score": round(keyword_score, 3),
        "hallucination_score": round(hallucination_score, 3),
        "generation_time_ms": round(generation_time * 1000),
    }


async def run_evaluation():
    """Run full RAG evaluation"""
    print("=" * 70)
    print("🧪 MindGraph RAG Evaluation")
    print("=" * 70)
    print(f"Test cases: {len(TEST_CASES)}")
    print(f"NULL_CASE_SIM_THRESHOLD: {NULL_CASE_SIM_THRESHOLD}")
    print()
    
    results = []
    total_retrieval_time = 0
    total_generation_time = 0
    total_f1 = 0
    total_keyword_score = 0
    total_hallucination_score = 0
    
    for i, test in enumerate(TEST_CASES, 1):
        category = test.get("category", "uncategorised")
        print(f"─── Test {i}/{len(TEST_CASES)} [{category}]: {test['question']}")

        # Step 1: Evaluate retrieval (entry_id based)
        retrieval = await evaluate_retrieval(
            test["question"],
            test.get("expected_entry_id"),
            category,
        )

        # Step 2: Get entries for answer generation
        query_embedding = await get_embedding(test["question"], task_type="RETRIEVAL_QUERY")
        entries_result = supabase.rpc("match_entries", {
            "query_embedding": query_embedding,
            "match_count": 5,
            "filter_user_id": USER_ID
        }).execute()

        # Step 3: Evaluate answer
        answer_eval = await evaluate_answer(
            test["question"],
            entries_result.data,
            test.get("expected_keywords", []),
            test.get("forbidden_keywords"),
        )

        # Print results
        rank_str = f"rank={retrieval['rank']}" if retrieval['rank'] else "miss"
        print(f"  Retrieval: hit={retrieval['hit']} ({rank_str}) | {retrieval['retrieval_time_ms']}ms")
        print(f"  Retrieved: {[t[:30] for t in retrieval['retrieved_titles']]}")
        print(f"  Answer:    Keywords={answer_eval['keyword_score']} | Hallucination={answer_eval['hallucination_score']} | {answer_eval['generation_time_ms']}ms")
        if answer_eval["keywords_missing"]:
            print(f"  ⚠ Missing:  {answer_eval['keywords_missing']}")
        if answer_eval["hallucinations"]:
            print(f"  ❌ Hallucinated: {answer_eval['hallucinations']}")
        print()
        
        # Accumulate totals
        total_retrieval_time += retrieval["retrieval_time_ms"]
        total_generation_time += answer_eval["generation_time_ms"]
        total_f1 += retrieval["f1_score"]
        total_keyword_score += answer_eval["keyword_score"]
        total_hallucination_score += answer_eval["hallucination_score"]
        
        results.append({
            "question": test["question"],
            "retrieval": retrieval,
            "answer": answer_eval,
        })
    
    # Summary
    n = len(TEST_CASES)
    print("=" * 70)
    print("📊 EVALUATION SUMMARY")
    print("=" * 70)
    print(f"  Total test cases:         {n}")
    print(f"  Avg Retrieval F1:         {round(total_f1 / n, 3)}")
    print(f"  Avg Keyword Score:        {round(total_keyword_score / n, 3)}")
    print(f"  Avg Hallucination Score:  {round(total_hallucination_score / n, 3)}")
    print(f"  Avg Retrieval Latency:    {round(total_retrieval_time / n)}ms")
    print(f"  Avg Generation Latency:   {round(total_generation_time / n)}ms")
    print(f"  Total Evaluation Time:    {round((total_retrieval_time + total_generation_time) / 1000, 1)}s")
    print("=" * 70)
    
    # MRR (Mean Reciprocal Rank) over non-null cases.
    # For each non-null case, RR = 1/rank if expected_entry_id is in top-K, else 0.
    # Null cases (hard_null) are excluded from MRR since "rank" is undefined.
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
    wall_clock_s = round((total_retrieval_time + total_generation_time) / 1000, 1)

    print("\n  Hit rate by category:")
    for cat in sorted(category_stats):
        cs = category_stats[cat]
        rate = round(cs["hits"] / cs["n"], 3) if cs["n"] else 0.0
        print(f"    {cat:14}: {cs['hits']}/{cs['n']} = {rate}")

    print(f"  MRR:                      {mrr}")
    print(f"  Pass rate (F1>0):         {pass_rate}")
    print(f"  Wall-clock:               {wall_clock_s}s")
    print("=" * 70)

    # Save results to JSON — repo root path kept for backwards-compat; also write
    # a tagged copy under evals/results/ for the task_type backfill comparison.
    summary = {
        "test_cases": n,
        "user_id": USER_ID,
        "null_case_sim_threshold": NULL_CASE_SIM_THRESHOLD,
        "avg_retrieval_f1": round(total_f1 / n, 3),
        "mrr": mrr,
        "mrr_scope": "non-null cases only",
        "pass_rate": pass_rate,
        "category_hit_rate": {
            cat: round(cs["hits"] / cs["n"], 3) if cs["n"] else 0.0
            for cat, cs in category_stats.items()
        },
        "avg_keyword_score": round(total_keyword_score / n, 3),
        "avg_hallucination_score": round(total_hallucination_score / n, 3),
        "avg_retrieval_latency_ms": round(total_retrieval_time / n),
        "avg_generation_latency_ms": round(total_generation_time / n),
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
# exist in any production user's DB (USER_ID e5e611e2-... only has 4 active
# entries). Every case scored F1=0 so the eval was non-measuring.
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