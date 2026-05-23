"""A/B/C eval for the normalize node thinking_budget parameter.

Compares thinking_budget in {0, 512, -1} on the existing 25-case normalize
harness. Each config is run N_RUNS times to estimate variance. Results are
printed as a comparison table and persisted as JSON under evals/results/.

Run: python -m evals.normalize_thinking_budget_eval
"""
import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI

import app.nodes.normalize as normalize_module
from app.nodes.normalize import normalize
from evals.normalize_evaluation import (
    FORMAT_LEAK_MARKERS,
    FrozenDateTime,
    TEST_CASES,
    build_state,
    contains_phrase,
    extract_dates,
    normalize_relaxed_text,
)


THINKING_BUDGETS = [0, 512, -1]
N_RUNS = 3
MODEL_NAME = "gemini-2.5-flash-lite"
TEMPERATURE = 0.1

# Gemini 2.5 Flash-Lite pricing (USD per 1M tokens). Thinking tokens are
# billed at the output rate.
PRICE_INPUT_PER_MTOK = 0.10
PRICE_OUTPUT_PER_MTOK = 0.40


class CapturingModel:
    """Wraps a ChatGoogleGenerativeAI to capture per-call response + latency."""

    def __init__(self, real_model):
        self._real = real_model
        self.last_response = None
        self.last_latency_ms = 0.0

    async def ainvoke(self, prompt):
        started = time.perf_counter()
        response = await self._real.ainvoke(prompt)
        self.last_latency_ms = (time.perf_counter() - started) * 1000
        self.last_response = response
        return response


async def _noop_embedding(_text):
    return None


def extract_usage(response) -> dict:
    """Pull token counts from a LangChain Gemini response, tolerating shapes."""
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


async def run_single_case(case: dict, capturing_model: CapturingModel) -> dict:
    FrozenDateTime.frozen_utc = case["reference_utc"]
    state = build_state(case)

    result = await normalize(state, model=capturing_model)
    output = result["cleaned_text"]
    latency_ms = capturing_model.last_latency_ms
    usage = extract_usage(capturing_model.last_response)

    expected_dates = case["expected_dates"]
    predicted_dates = extract_dates(output)
    predicted_set = set(predicted_dates)
    expected_set = set(expected_dates)

    missing_required = [
        phrase for phrase in case["must_contain"] if not contains_phrase(output, phrase)
    ]
    forbidden_hits = [
        phrase for phrase in case["must_not_contain"] if contains_phrase(output, phrase)
    ]
    format_clean = not any(marker in output.lower() for marker in FORMAT_LEAK_MARKERS)

    date_set_exact = predicted_set == expected_set
    no_date_hallucination = (not expected_dates) and (not predicted_dates)
    functional_pass = (
        date_set_exact
        and not missing_required
        and not forbidden_hits
        and format_clean
    )

    return {
        "name": case["name"],
        "family": case["family"],
        "difficulty": case["difficulty"],
        "user_timezone": case["user_timezone"],
        "reference_utc": case["reference_utc"].isoformat(),
        "latency_ms": latency_ms,
        "output": output,
        "expected_output": case["expected_output"],
        "predicted_dates": predicted_dates,
        "expected_dates": expected_dates,
        "date_set_exact": date_set_exact,
        "no_date_hallucination": no_date_hallucination,
        "no_date_case": not expected_dates,
        "missing_required": missing_required,
        "forbidden_hits": forbidden_hits,
        "format_clean": format_clean,
        "functional_pass": functional_pass,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "thoughts_tokens": usage["thoughts_tokens"],
    }


def run_metrics(run_results: list[dict]) -> dict:
    total = len(run_results)
    no_date_results = [r for r in run_results if r["no_date_case"]]
    hallucinated = sum(1 for r in no_date_results if not r["no_date_hallucination"])
    return {
        "functional_pass_rate": sum(r["functional_pass"] for r in run_results) / total,
        "date_case_accuracy": sum(r["date_set_exact"] for r in run_results) / total,
        "no_date_hallucination_rate": (
            hallucinated / len(no_date_results) if no_date_results else 0.0
        ),
        "avg_latency_ms": statistics.mean(r["latency_ms"] for r in run_results),
        "avg_thinking_tokens": statistics.mean(r["thoughts_tokens"] for r in run_results),
        "avg_output_tokens": statistics.mean(r["output_tokens"] for r in run_results),
        "avg_input_tokens": statistics.mean(r["input_tokens"] for r in run_results),
        "total_input_tokens": sum(r["input_tokens"] for r in run_results),
        "total_output_tokens": sum(r["output_tokens"] for r in run_results),
        "total_thoughts_tokens": sum(r["thoughts_tokens"] for r in run_results),
    }


def aggregate_runs(per_run_metrics: list[dict]) -> dict:
    keys = [
        "functional_pass_rate",
        "date_case_accuracy",
        "no_date_hallucination_rate",
        "avg_latency_ms",
        "avg_thinking_tokens",
        "avg_output_tokens",
        "avg_input_tokens",
    ]
    summary = {}
    for key in keys:
        values = [m[key] for m in per_run_metrics]
        summary[key] = {
            "mean": statistics.mean(values),
            "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
        }
    summary["total_input_tokens"] = sum(m["total_input_tokens"] for m in per_run_metrics)
    summary["total_output_tokens"] = sum(m["total_output_tokens"] for m in per_run_metrics)
    summary["total_thoughts_tokens"] = sum(m["total_thoughts_tokens"] for m in per_run_metrics)
    return summary


def fmt_pct(mean: float, stddev: float) -> str:
    return f"{mean * 100:6.2f}% ± {stddev * 100:5.2f}%"


def fmt_num(mean: float, stddev: float, decimals: int = 1) -> str:
    return f"{mean:7.{decimals}f} ± {stddev:6.{decimals}f}"


def print_comparison_table(by_config: dict) -> str:
    lines = []
    header = (
        f"{'thinking_budget':>16} | "
        f"{'functional_pass':>17} | "
        f"{'date_accuracy':>17} | "
        f"{'no_date_halluc':>17} | "
        f"{'latency_ms':>20} | "
        f"{'thinking_toks':>20} | "
        f"{'output_toks':>20}"
    )
    sep = "-" * len(header)
    lines.append(header)
    lines.append(sep)
    for budget, summary in by_config.items():
        fp = summary["functional_pass_rate"]
        da = summary["date_case_accuracy"]
        nd = summary["no_date_hallucination_rate"]
        lat = summary["avg_latency_ms"]
        tt = summary["avg_thinking_tokens"]
        ot = summary["avg_output_tokens"]
        line = (
            f"{str(budget):>16} | "
            f"{fmt_pct(fp['mean'], fp['stddev']):>17} | "
            f"{fmt_pct(da['mean'], da['stddev']):>17} | "
            f"{fmt_pct(nd['mean'], nd['stddev']):>17} | "
            f"{fmt_num(lat['mean'], lat['stddev'], 1):>20} | "
            f"{fmt_num(tt['mean'], tt['stddev'], 1):>20} | "
            f"{fmt_num(ot['mean'], ot['stddev'], 1):>20}"
        )
        lines.append(line)
    table = "\n".join(lines)
    print(table)
    return table


def compute_cost(by_config: dict) -> float:
    total_input = sum(s["total_input_tokens"] for s in by_config.values())
    total_output = sum(s["total_output_tokens"] for s in by_config.values())
    total_thoughts = sum(s["total_thoughts_tokens"] for s in by_config.values())
    input_cost = (total_input / 1_000_000) * PRICE_INPUT_PER_MTOK
    output_cost = ((total_output + total_thoughts) / 1_000_000) * PRICE_OUTPUT_PER_MTOK
    return input_cost + output_cost


async def main() -> None:
    overall_start = time.perf_counter()

    # Patch embeddings to a no-op so the eval only measures the LLM call.
    original_get_embedding = normalize_module.get_embedding
    normalize_module.get_embedding = _noop_embedding
    # Freeze datetime so cases land on their reference dates.
    original_datetime = normalize_module.datetime
    normalize_module.datetime = FrozenDateTime

    raw_results: dict[int, list[list[dict]]] = {}
    by_config_metrics: dict[int, list[dict]] = {}
    total_calls = 0

    try:
        for budget in THINKING_BUDGETS:
            real_model = ChatGoogleGenerativeAI(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                thinking_budget=budget,
            )
            capturing = CapturingModel(real_model)

            print(f"\n>>> Running thinking_budget={budget} ({N_RUNS} runs x {len(TEST_CASES)} cases)")
            raw_results[budget] = []
            by_config_metrics[budget] = []

            for run_index in range(N_RUNS):
                run_results = []
                for case in TEST_CASES:
                    result = await run_single_case(case, capturing)
                    run_results.append(result)
                    total_calls += 1
                raw_results[budget].append(run_results)
                metrics = run_metrics(run_results)
                by_config_metrics[budget].append(metrics)
                print(
                    f"    run {run_index + 1}/{N_RUNS}: "
                    f"functional_pass={metrics['functional_pass_rate']:.2%}, "
                    f"date_acc={metrics['date_case_accuracy']:.2%}, "
                    f"avg_latency_ms={metrics['avg_latency_ms']:.1f}, "
                    f"avg_thinking_toks={metrics['avg_thinking_tokens']:.1f}"
                )
    finally:
        normalize_module.datetime = original_datetime
        normalize_module.get_embedding = original_get_embedding

    by_config_summary = {
        budget: aggregate_runs(by_config_metrics[budget])
        for budget in THINKING_BUDGETS
    }

    total_runtime_s = time.perf_counter() - overall_start
    estimated_cost = compute_cost(by_config_summary)

    print("\n" + "=" * 140)
    print("NORMALIZE NODE — THINKING_BUDGET A/B/C")
    print("=" * 140)
    print(f"Total API calls       : {total_calls}")
    print(f"Estimated cost (USD)  : ${estimated_cost:.6f}")
    print(f"Total wall-clock (s)  : {total_runtime_s:.1f}")
    print(
        f"Model={MODEL_NAME}, temperature={TEMPERATURE}, N_RUNS={N_RUNS}, "
        f"cases per run={len(TEST_CASES)}"
    )
    print()
    table = print_comparison_table(by_config_summary)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"normalize_thinking_budget_{timestamp}.json"

    payload = {
        "generated_utc": timestamp,
        "model": MODEL_NAME,
        "temperature": TEMPERATURE,
        "n_runs": N_RUNS,
        "cases_per_run": len(TEST_CASES),
        "total_calls": total_calls,
        "estimated_cost_usd": estimated_cost,
        "total_runtime_s": total_runtime_s,
        "pricing": {
            "input_per_mtok": PRICE_INPUT_PER_MTOK,
            "output_per_mtok": PRICE_OUTPUT_PER_MTOK,
        },
        "by_config": {str(k): v for k, v in by_config_summary.items()},
        "per_run_metrics": {
            str(budget): by_config_metrics[budget] for budget in THINKING_BUDGETS
        },
        "raw_results": {
            str(budget): raw_results[budget] for budget in THINKING_BUDGETS
        },
        "comparison_table": table,
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"\nWrote raw results to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
