"""A/B eval: does thinking_budget=0 increase extract_relations output verbosity?

Background: the 30-day Langfuse diff showed extract_relations mean output tokens
jumped +189% (48 -> 139) after thinking_budget=0 was deployed. All other nodes
stayed flat or improved. Two competing hypotheses:

    1. Removing thinking made the model more verbose (would falsify the
       thinking_budget=0 decision for this node).
    2. The recent test entries happened to be relationship-denser than the
       historical mean (just sampling noise).

This eval pins the inputs and varies only thinking_budget. If hypothesis (1) is
true, mean output tokens will jump on the same fixed inputs.

Run: python -m evals.extract_relations_thinking_budget_eval
"""
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

load_dotenv(encoding="utf-8-sig")

from langchain_google_genai import ChatGoogleGenerativeAI

from app.llm import extract_text
from app.nodes.extract_relations import build_relations_prompt, parse_relations


THINKING_BUDGETS = [0, -1]
N_RUNS = 3
MODEL_NAME = "gemini-2.5-flash-lite"
TEMPERATURE = 0.1

# Gemini 2.5 Flash-Lite pricing (USD per 1M tokens). Thinking billed as output.
PRICE_INPUT_PER_MTOK = 0.10
PRICE_OUTPUT_PER_MTOK = 0.40

# Verdict thresholds.
ATTRIBUTION_DELTA_PCT = 20.0  # |delta| must exceed this to be attributable
# Difference between configs must also exceed 1 stddev of either config.


# ---- Test cases ----------------------------------------------------------
# Spread across relationship density. `expected_relation_count` is the
# ground-truth count; the model may emit fewer (it caps at 5) or extras.
TEST_CASES = [
    # ---- 0 expected relations (2 cases) ----
    {
        "id": "case_01_single_entity",
        "expected_relation_count": 0,
        "cleaned_text": "I went for a long walk in the morning and felt calm afterward.",
        "core_entities": [
            {"name": "I", "type": "person"},
        ],
    },
    {
        "id": "case_02_unrelated_entities",
        "expected_relation_count": 0,
        "cleaned_text": (
            "Read an article about France in the morning. Later watched a tutorial "
            "about Notion. The two had nothing in common."
        ),
        "core_entities": [
            {"name": "France", "type": "place"},
            {"name": "Notion", "type": "tool"},
        ],
    },
    # ---- 1-2 expected relations (3 cases) ----
    {
        "id": "case_03_built_with",
        "expected_relation_count": 1,
        "cleaned_text": "Built MindGraph using Figma over the weekend.",
        "core_entities": [
            {"name": "MindGraph", "type": "project"},
            {"name": "Figma", "type": "tool"},
        ],
    },
    {
        "id": "case_04_located_at",
        "expected_relation_count": 1,
        "cleaned_text": "Met Rahul at the Bengaluru office for the design review.",
        "core_entities": [
            {"name": "Rahul", "type": "person"},
            {"name": "Bengaluru", "type": "place"},
        ],
    },
    {
        "id": "case_05_two_relations",
        "expected_relation_count": 2,
        "cleaned_text": (
            "I worked on MindGraph using LangGraph in the afternoon. "
            "Made good progress on the dedup node."
        ),
        "core_entities": [
            {"name": "I", "type": "person"},
            {"name": "MindGraph", "type": "project"},
            {"name": "LangGraph", "type": "tool"},
        ],
    },
    # ---- 3-5 expected relations (3 cases) ----
    {
        "id": "case_06_medium_5rel",
        "expected_relation_count": 5,
        "cleaned_text": (
            "Spent the morning at Inspiral with Sahana working on MindGraph "
            "using Cursor. Felt productive."
        ),
        "core_entities": [
            {"name": "I", "type": "person"},
            {"name": "Sahana", "type": "person"},
            {"name": "Inspiral", "type": "place"},
            {"name": "MindGraph", "type": "project"},
            {"name": "Cursor", "type": "tool"},
        ],
    },
    {
        "id": "case_07_three_relations",
        "expected_relation_count": 3,
        "cleaned_text": (
            "Naveen recommended Slack for team coordination at Simplico. "
            "Said the async culture works well there."
        ),
        "core_entities": [
            {"name": "Naveen", "type": "person"},
            {"name": "Slack", "type": "tool"},
            {"name": "Simplico", "type": "organization"},
        ],
    },
    {
        "id": "case_08_event_planning",
        "expected_relation_count": 4,
        "cleaned_text": (
            "Started planning the Goa retreat with Priya. We'll use Notion "
            "for the itinerary and book flights through Cleartrip."
        ),
        "core_entities": [
            {"name": "I", "type": "person"},
            {"name": "Priya", "type": "person"},
            {"name": "Goa retreat", "type": "event"},
            {"name": "Goa", "type": "place"},
            {"name": "Notion", "type": "tool"},
            {"name": "Cleartrip", "type": "tool"},
        ],
    },
    # ---- 6+ expected relations (2 cases) ----
    {
        "id": "case_09_simplico_dense",
        "expected_relation_count": 7,
        "cleaned_text": (
            "Joined Simplico as a contractor. Manuel onboarded me. We use "
            "Notion for docs, Slack for chat, GitHub for code, and Linear "
            "for tickets. The team sits in the Bengaluru office."
        ),
        "core_entities": [
            {"name": "I", "type": "person"},
            {"name": "Manuel", "type": "person"},
            {"name": "Simplico", "type": "organization"},
            {"name": "Notion", "type": "tool"},
            {"name": "Slack", "type": "tool"},
            {"name": "GitHub", "type": "tool"},
            {"name": "Linear", "type": "tool"},
            {"name": "Bengaluru", "type": "place"},
        ],
    },
    {
        "id": "case_10_mindgraph_stack",
        "expected_relation_count": 8,
        "cleaned_text": (
            "Pitched MindGraph to Anthropic. Built it with Python, LangGraph, "
            "Supabase, pgvector, and React. Demo went well. Sridhar joined "
            "the call from the Mumbai office."
        ),
        "core_entities": [
            {"name": "I", "type": "person"},
            {"name": "Sridhar", "type": "person"},
            {"name": "MindGraph", "type": "project"},
            {"name": "Anthropic", "type": "organization"},
            {"name": "Python", "type": "tool"},
            {"name": "LangGraph", "type": "tool"},
            {"name": "Supabase", "type": "tool"},
            {"name": "pgvector", "type": "tool"},
            {"name": "React", "type": "tool"},
            {"name": "Mumbai", "type": "place"},
        ],
    },
]


# ---- Helpers -------------------------------------------------------------
def extract_usage(response) -> dict:
    """Pull input/output/thinking tokens from a LangChain Gemini response."""
    input_tokens = 0
    output_tokens = 0
    thoughts_tokens = 0

    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens") or 0
        output_tokens = usage.get("output_tokens") or 0
        details = usage.get("output_token_details") or {}
        if isinstance(details, dict):
            thoughts_tokens = details.get("reasoning") or 0

    resp_meta = getattr(response, "response_metadata", None) or {}
    raw_usage = resp_meta.get("usage_metadata") if isinstance(resp_meta, dict) else None
    if isinstance(raw_usage, dict):
        if not input_tokens:
            input_tokens = raw_usage.get("prompt_token_count") or 0
        if not output_tokens:
            output_tokens = raw_usage.get("candidates_token_count") or 0
        if not thoughts_tokens:
            thoughts_tokens = raw_usage.get("thoughts_token_count") or 0

    return {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "thoughts_tokens": int(thoughts_tokens or 0),
    }


async def run_one_call(model, case: dict) -> dict:
    prompt = build_relations_prompt(case["cleaned_text"], case["core_entities"])
    started = time.perf_counter()
    response = await model.ainvoke(prompt)
    latency_ms = (time.perf_counter() - started) * 1000.0
    text = extract_text(response)
    parsed = parse_relations(text, case["core_entities"])
    usage = extract_usage(response)
    return {
        "case_id": case["id"],
        "expected_relation_count": case["expected_relation_count"],
        "parsed_relation_count": len(parsed),
        "latency_ms": latency_ms,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "thoughts_tokens": usage["thoughts_tokens"],
        "raw_output_chars": len(text),
        "parsed_output": parsed,
    }


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return float(values[0]), 0.0
    return statistics.mean(values), statistics.stdev(values)


def compute_cost(per_call: list[dict]) -> float:
    total_in = sum(c["input_tokens"] for c in per_call)
    total_out = sum(c["output_tokens"] for c in per_call)
    total_thoughts = sum(c["thoughts_tokens"] for c in per_call)
    return (
        (total_in / 1_000_000) * PRICE_INPUT_PER_MTOK
        + ((total_out + total_thoughts) / 1_000_000) * PRICE_OUTPUT_PER_MTOK
    )


def fmt(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def fmt_pct(value: float) -> str:
    return f"{value:+.1f}%"


async def main() -> None:
    overall_start = time.perf_counter()

    # results[budget][case_id] = list of N call dicts
    results: dict[int, dict[str, list[dict]]] = {b: {} for b in THINKING_BUDGETS}
    per_config_all: dict[int, list[dict]] = {b: [] for b in THINKING_BUDGETS}
    total_calls = 0

    for budget in THINKING_BUDGETS:
        model = ChatGoogleGenerativeAI(
            model=MODEL_NAME, temperature=TEMPERATURE, thinking_budget=budget
        )
        print(
            f"\n>>> thinking_budget={budget} | {N_RUNS} runs x {len(TEST_CASES)} cases = "
            f"{N_RUNS * len(TEST_CASES)} calls"
        )
        for case in TEST_CASES:
            case_results = []
            for rep in range(N_RUNS):
                call = await run_one_call(model, case)
                case_results.append(call)
                per_config_all[budget].append(call)
                total_calls += 1
            results[budget][case["id"]] = case_results
            out_mean, out_std = mean_std([c["output_tokens"] for c in case_results])
            parsed_mean, _ = mean_std([c["parsed_relation_count"] for c in case_results])
            print(
                f"    {case['id']:<28} expected={case['expected_relation_count']} "
                f"parsed_mean={parsed_mean:.1f} output_toks={out_mean:.1f}±{out_std:.1f}"
            )

    total_runtime_s = time.perf_counter() - overall_start
    all_calls = [c for calls in per_config_all.values() for c in calls]
    cost_total = compute_cost(all_calls)

    # ---- Per-case table ----
    print("\n" + "=" * 130)
    print("EXTRACT_RELATIONS THINKING_BUDGET A/B EVAL")
    print("=" * 130)
    print(f"Total API calls       : {total_calls}")
    print(f"Estimated cost (USD)  : ${cost_total:.6f}")
    print(f"Total wall-clock (s)  : {total_runtime_s:.1f}")
    print(
        f"Model={MODEL_NAME}, temperature={TEMPERATURE}, N_RUNS={N_RUNS}, "
        f"cases={len(TEST_CASES)}"
    )

    print("\n--- PER-CASE OUTPUT TOKENS (mean ± stddev across N=3 runs) ---")
    header = (
        f"{'case_id':<28} | {'expected':>8} | "
        f"{'tb=0 out_toks':>17} | {'tb=-1 out_toks':>18} | "
        f"{'delta_abs':>10} | {'delta_pct':>10}"
    )
    print(header)
    print("-" * len(header))
    for case in TEST_CASES:
        cid = case["id"]
        tb0 = [c["output_tokens"] for c in results[0][cid]]
        tbm = [c["output_tokens"] for c in results[-1][cid]]
        tb0_mean, tb0_std = mean_std(tb0)
        tbm_mean, tbm_std = mean_std(tbm)
        delta_abs = tb0_mean - tbm_mean
        delta_pct = (delta_abs / tbm_mean * 100) if tbm_mean else 0.0
        print(
            f"{cid:<28} | {case['expected_relation_count']:>8} | "
            f"{tb0_mean:>7.1f} ± {tb0_std:>5.1f}  | "
            f"{tbm_mean:>8.1f} ± {tbm_std:>5.1f}  | "
            f"{delta_abs:>+10.1f} | {fmt_pct(delta_pct):>10}"
        )

    # ---- Per-config summary ----
    print("\n--- PER-CONFIG SUMMARY (across all cases x runs) ---")
    summary_per_config: dict[int, dict] = {}
    for budget in THINKING_BUDGETS:
        calls = per_config_all[budget]
        out_vals = [c["output_tokens"] for c in calls]
        lat_vals = [c["latency_ms"] for c in calls]
        thoughts = sum(c["thoughts_tokens"] for c in calls)
        out_mean, out_std = mean_std(out_vals)
        lat_mean, lat_std = mean_std(lat_vals)
        summary_per_config[budget] = {
            "mean_output_tokens": out_mean,
            "stddev_output_tokens": out_std,
            "mean_latency_ms": lat_mean,
            "stddev_latency_ms": lat_std,
            "total_thoughts_tokens": thoughts,
            "n_calls": len(calls),
        }
        label = f"thinking_budget={budget}"
        print(
            f"  {label:<22} n={len(calls):<3} "
            f"output_toks_mean={out_mean:7.1f} ± {out_std:5.1f}  "
            f"latency_ms_mean={lat_mean:7.1f} ± {lat_std:5.1f}  "
            f"total_thinking_toks={thoughts}"
        )

    # ---- Verdict ----
    tb0_summary = summary_per_config[0]
    tbm_summary = summary_per_config[-1]
    tb0_mean = tb0_summary["mean_output_tokens"]
    tbm_mean = tbm_summary["mean_output_tokens"]
    delta_abs = tb0_mean - tbm_mean
    delta_pct = (delta_abs / tbm_mean * 100) if tbm_mean else 0.0

    bigger_stddev = max(
        tb0_summary["stddev_output_tokens"], tbm_summary["stddev_output_tokens"]
    )
    exceeds_threshold = abs(delta_pct) > ATTRIBUTION_DELTA_PCT
    exceeds_noise = abs(delta_abs) > bigger_stddev
    attributable = exceeds_threshold and exceeds_noise

    direction = "thinking_budget=0 OUTPUTS MORE" if delta_abs > 0 else "thinking_budget=0 OUTPUTS LESS"
    if abs(delta_abs) < 1:
        direction = "no meaningful difference"

    verdict = "attributable to thinking_budget" if attributable else "NOT attributable to thinking_budget"
    print("\n--- VERDICT ---")
    print(
        f"OUTPUT TOKENS DELTA: {fmt_pct(delta_pct)} "
        f"({tb0_mean:.1f} vs {tbm_mean:.1f}, abs={delta_abs:+.1f}) "
        f"— {verdict}"
    )
    print(
        f"  threshold check  : |delta|={abs(delta_pct):.1f}% "
        f"{'>' if exceeds_threshold else '<='} {ATTRIBUTION_DELTA_PCT}% required"
    )
    print(
        f"  noise check      : |abs_delta|={abs(delta_abs):.1f} tokens "
        f"{'>' if exceeds_noise else '<='} larger stddev={bigger_stddev:.1f}"
    )
    print(f"  direction        : {direction}")

    # ---- Persist ----
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"extract_relations_thinking_budget_{timestamp}.json"
    payload = {
        "generated_utc": timestamp,
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "n_runs": N_RUNS,
        "n_cases": len(TEST_CASES),
        "n_total_calls": total_calls,
        "estimated_cost_usd": cost_total,
        "total_runtime_s": total_runtime_s,
        "pricing": {
            "input_per_mtok": PRICE_INPUT_PER_MTOK,
            "output_per_mtok": PRICE_OUTPUT_PER_MTOK,
        },
        "test_cases": TEST_CASES,
        "per_config_summary": {str(k): v for k, v in summary_per_config.items()},
        "per_case_results": {
            str(budget): results[budget] for budget in THINKING_BUDGETS
        },
        "verdict": {
            "delta_abs_tokens": delta_abs,
            "delta_pct": delta_pct,
            "exceeds_pct_threshold": exceeds_threshold,
            "exceeds_noise": exceeds_noise,
            "attributable": attributable,
            "direction": direction,
        },
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
    print(f"\nWrote raw results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
