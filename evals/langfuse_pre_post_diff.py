"""Before/after metrics diff for a pipeline change, using Langfuse trace data.

Use case: on 23/05/2026 we set `thinking_budget=0` on `flash` and `flash_creative`.
This script pulls observations from Langfuse in symmetric windows around a cutoff
timestamp and shows the per-node latency / token / cost delta so the claim can be
verified against real trace data instead of trusted on faith.

Usage:
    python -m evals.langfuse_pre_post_diff --cutoff 2026-05-23T10:30:00Z
    python -m evals.langfuse_pre_post_diff --cutoff 2026-05-23T10:30:00Z --window 48

Env vars (same as the rest of the app):
    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
"""
import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Force UTF-8 stdout so the table prints cleanly on Windows consoles too.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

load_dotenv(encoding="utf-8-sig")

try:
    from langfuse import Langfuse
except ImportError as exc:
    print(f"ERROR: langfuse package required: {exc}", file=sys.stderr)
    sys.exit(1)


# Pipeline nodes that produce an LLM call. Skip dedup and store (no LLM).
NODE_NAMES = [
    "normalize",
    "classify",
    "extract_entities",
    "extract_relations",
    "deadline",
    "title_summary",
]

# Fallback Gemini 2.5 Flash-Lite pricing (USD per 1M tokens). Used only if a
# row has total_cost=None (e.g. when Langfuse has no model definition).
PRICE_INPUT_PER_MTOK = 0.10
PRICE_OUTPUT_PER_MTOK = 0.40

# Fields requested from Langfuse — only what we need.
FIELDS = "core,basic,usage,metrics,model"

# Maximum observations per page. Langfuse cap is typically 100.
PAGE_LIMIT = 100


def parse_cutoff(value: str) -> datetime:
    """Parse an ISO 8601 cutoff timestamp. Accepts trailing Z for UTC."""
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise SystemExit(f"--cutoff is not a valid ISO 8601 timestamp: {value}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _paginated(client: Langfuse, **base_kwargs) -> list:
    """Fully paginate one observations.get_many query."""
    results = []
    cursor = None
    while True:
        kwargs = dict(base_kwargs)
        kwargs["fields"] = FIELDS
        kwargs["limit"] = PAGE_LIMIT
        if cursor:
            kwargs["cursor"] = cursor
        response = client.api.observations.get_many(**kwargs)
        page = list(response.data or [])
        results.extend(page)
        next_cursor = getattr(response.meta, "cursor", None) if response.meta else None
        if not next_cursor or not page:
            break
        if next_cursor == cursor:
            # Safety net against an API that returns the same cursor in a loop.
            break
        cursor = next_cursor
    return results


def fetch_observations(
    client: Langfuse, name: str, from_time: datetime, to_time: datetime
) -> list:
    """Fetch every observation with `name` in [from_time, to_time], paginating."""
    return _paginated(
        client, name=name, from_start_time=from_time, to_start_time=to_time
    )


def fetch_all_generations(
    client: Langfuse, from_time: datetime, to_time: datetime
) -> list:
    """Fetch every GENERATION observation in [from_time, to_time], paginating.

    One bulk call per window instead of one per chain — much faster.
    """
    return _paginated(
        client,
        type="GENERATION",
        from_start_time=from_time,
        to_start_time=to_time,
    )


def index_generations_by_parent(generations: list) -> dict[str, list]:
    index: dict[str, list] = {}
    for gen in generations:
        parent_id = getattr(gen, "parent_observation_id", None)
        if not parent_id:
            continue
        index.setdefault(parent_id, []).append(gen)
    return index


def aggregate_children_usage(children: list) -> tuple[int, int, float, bool]:
    """Sum input/output tokens and cost across child generations.

    Returns (input_tokens, output_tokens, cost_usd, any_cost_computed).
    """
    in_total = 0
    out_total = 0
    cost_total = 0.0
    any_computed = False
    for child in children:
        # Only count generations (skip nested chains / sub-spans).
        ctype = getattr(child, "type", None)
        if ctype and str(ctype).upper() != "GENERATION":
            continue
        usage = getattr(child, "usage_details", None)
        in_tok, out_tok = extract_tokens(usage)
        in_total += in_tok
        out_total += out_tok
        cost, computed = resolve_cost(child, in_tok, out_tok)
        cost_total += cost
        any_computed = any_computed or computed
    return in_total, out_total, cost_total, any_computed


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return ordered[index]


def extract_tokens(usage_details) -> tuple[int, int]:
    """Pull (input_tokens, output_tokens) from a usage_details dict, tolerating shapes.

    Langfuse output_tokens for Gemini thinking models includes reasoning tokens.
    """
    if not isinstance(usage_details, dict):
        return 0, 0
    input_tokens = (
        usage_details.get("input")
        or usage_details.get("input_tokens")
        or usage_details.get("prompt_tokens")
        or usage_details.get("prompt_token_count")
        or 0
    )
    output_tokens = (
        usage_details.get("output")
        or usage_details.get("output_tokens")
        or usage_details.get("completion_tokens")
        or usage_details.get("candidates_token_count")
        or 0
    )
    return int(input_tokens or 0), int(output_tokens or 0)


def resolve_cost(obs, input_tokens: int, output_tokens: int) -> tuple[float, bool]:
    """Return (cost_usd, computed_from_fallback). Prefers Langfuse total_cost."""
    total = getattr(obs, "total_cost", None)
    if total is not None:
        try:
            return float(total), False
        except (TypeError, ValueError):
            pass
    fallback = (
        (input_tokens / 1_000_000) * PRICE_INPUT_PER_MTOK
        + (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_MTOK
    )
    return fallback, True


def summarize(per_call: list[dict]) -> dict:
    """Aggregate latency / token / cost metrics for one (node, window) bucket.

    Expects a list of per-call dicts produced by `build_per_call_metrics`.
    """
    if not per_call:
        return {
            "count": 0,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
            "mean_input_tokens": None,
            "mean_output_tokens": None,
            "total_cost_usd": 0.0,
            "mean_cost_per_call_usd": None,
            "any_cost_computed": False,
        }

    latencies_ms = [c["latency_ms"] for c in per_call if c["latency_ms"] is not None]
    input_tokens_list = [c["input_tokens"] for c in per_call]
    output_tokens_list = [c["output_tokens"] for c in per_call]
    per_call_cost = [c["cost_usd"] for c in per_call]
    any_computed = any(c["cost_computed"] for c in per_call)

    return {
        "count": len(per_call),
        "p50_latency_ms": percentile(latencies_ms, 0.50) if latencies_ms else None,
        "p95_latency_ms": percentile(latencies_ms, 0.95) if latencies_ms else None,
        "mean_input_tokens": (
            statistics.mean(input_tokens_list) if input_tokens_list else None
        ),
        "mean_output_tokens": (
            statistics.mean(output_tokens_list) if output_tokens_list else None
        ),
        "total_cost_usd": sum(per_call_cost),
        "mean_cost_per_call_usd": (
            statistics.mean(per_call_cost) if per_call_cost else None
        ),
        "any_cost_computed": any_computed,
    }


def build_per_call_metrics(
    chain_observations: list, gen_index: dict[str, list]
) -> list[dict]:
    """For each chain observation, look up its child generations in the pre-built
    index and roll up the metrics.

    Latency comes from the chain (whole-node duration). Tokens and cost are summed
    from the chain's child GENERATION observations (the actual LLM calls).
    """
    metrics = []
    for chain in chain_observations:
        chain_id = getattr(chain, "id", None)
        latency_s = getattr(chain, "latency", None)
        latency_ms = None
        if latency_s is not None:
            try:
                latency_ms = float(latency_s) * 1000.0
            except (TypeError, ValueError):
                pass

        # If the chain itself has usage data (rare for CHAIN-type, but happens for
        # GENERATION-type when a node directly emits a generation), use it.
        chain_usage = getattr(chain, "usage_details", None) or {}
        chain_in, chain_out = extract_tokens(chain_usage)

        children = gen_index.get(chain_id, []) if chain_id else []
        children_in, children_out, children_cost, any_computed = (
            aggregate_children_usage(children)
        )

        # Prefer child-sum if non-zero, else fall back to chain-level (or fallback price).
        if children_in or children_out or children_cost:
            in_tok, out_tok, cost = children_in, children_out, children_cost
        else:
            in_tok, out_tok = chain_in, chain_out
            cost_val, computed = resolve_cost(chain, in_tok, out_tok)
            cost = cost_val
            any_computed = any_computed or computed

        metrics.append({
            "chain_id": chain_id,
            "trace_id": getattr(chain, "trace_id", None),
            "latency_ms": latency_ms,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": cost,
            "cost_computed": any_computed,
            "n_child_generations": len(children),
        })
    return metrics


def delta(before, after) -> tuple[str, str]:
    """Return (abs_delta_str, pct_delta_str). Handles None gracefully."""
    if before is None or after is None:
        return "n/a", "n/a"
    try:
        diff = after - before
        if before == 0:
            return f"{diff:+.2f}", "n/a"
        pct = (diff / before) * 100
        return f"{diff:+.2f}", f"{pct:+.1f}%"
    except (TypeError, ValueError):
        return "n/a", "n/a"


def fmt(value, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}"


def print_node_block(node: str, before: dict, after: dict) -> None:
    print(f"\n=== {node} ===")
    if before["count"] == 0 and after["count"] == 0:
        print(f"  WARNING: 0 observations in both windows. Skipping.")
        return
    if before["count"] == 0:
        print(f"  WARNING: 0 observations in BEFORE window (only after has {after['count']}).")
    if after["count"] == 0:
        print(f"  WARNING: 0 observations in AFTER window (only before has {before['count']}).")

    rows = [
        ("count", before["count"], after["count"], 0),
        ("p50 latency (ms)", before["p50_latency_ms"], after["p50_latency_ms"], 1),
        ("p95 latency (ms)", before["p95_latency_ms"], after["p95_latency_ms"], 1),
        ("mean input toks", before["mean_input_tokens"], after["mean_input_tokens"], 1),
        ("mean output toks", before["mean_output_tokens"], after["mean_output_tokens"], 1),
        ("total cost (USD)", before["total_cost_usd"], after["total_cost_usd"], 6),
        ("mean cost/call (USD)", before["mean_cost_per_call_usd"], after["mean_cost_per_call_usd"], 6),
    ]
    print(f"  {'metric':<22} | {'before':>14} | {'after':>14} | {'delta':>12} | {'delta%':>8}")
    print(f"  {'-'*22}-+-{'-'*14}-+-{'-'*14}-+-{'-'*12}-+-{'-'*8}")
    for label, b, a, decimals in rows:
        abs_d, pct_d = delta(b, a)
        print(
            f"  {label:<22} | {fmt(b, decimals):>14} | {fmt(a, decimals):>14} | "
            f"{abs_d:>12} | {pct_d:>8}"
        )
    if before["any_cost_computed"] or after["any_cost_computed"]:
        print(
            "  note: some cost values computed from fallback pricing "
            f"(input ${PRICE_INPUT_PER_MTOK}/Mtok, output ${PRICE_OUTPUT_PER_MTOK}/Mtok) "
            "because Langfuse total_cost was unavailable."
        )


def print_totals(per_node_before: dict, per_node_after: dict) -> None:
    def aggregate(side: dict) -> dict:
        counts = [s["count"] for s in side.values()]
        total_count = sum(counts)
        total_cost = sum(s["total_cost_usd"] for s in side.values())
        # Weighted mean latency across all calls.
        weighted_p50_sum = 0.0
        weighted_count = 0
        for s in side.values():
            if s["count"] and s["p50_latency_ms"] is not None:
                weighted_p50_sum += s["p50_latency_ms"] * s["count"]
                weighted_count += s["count"]
        weighted_p50 = (weighted_p50_sum / weighted_count) if weighted_count else None
        return {
            "total_count": total_count,
            "total_cost_usd": total_cost,
            "weighted_p50_latency_ms": weighted_p50,
        }

    before_total = aggregate(per_node_before)
    after_total = aggregate(per_node_after)

    print("\n=== TOTALS (across all listed nodes) ===")
    rows = [
        ("total calls", before_total["total_count"], after_total["total_count"], 0),
        (
            "weighted p50 latency (ms)",
            before_total["weighted_p50_latency_ms"],
            after_total["weighted_p50_latency_ms"],
            1,
        ),
        ("total cost (USD)", before_total["total_cost_usd"], after_total["total_cost_usd"], 6),
    ]
    print(f"  {'metric':<28} | {'before':>14} | {'after':>14} | {'delta':>12} | {'delta%':>8}")
    print(f"  {'-'*28}-+-{'-'*14}-+-{'-'*14}-+-{'-'*12}-+-{'-'*8}")
    for label, b, a, decimals in rows:
        abs_d, pct_d = delta(b, a)
        print(
            f"  {label:<28} | {fmt(b, decimals):>14} | {fmt(a, decimals):>14} | "
            f"{abs_d:>12} | {pct_d:>8}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diff Langfuse trace metrics around a pipeline change cutoff."
    )
    parser.add_argument(
        "--cutoff",
        required=True,
        help="ISO 8601 UTC timestamp when the change went live (e.g. 2026-05-23T10:30:00Z).",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=24.0,
        help="Hours on each side of the cutoff (default: 24).",
    )
    args = parser.parse_args()

    cutoff = parse_cutoff(args.cutoff)
    window = timedelta(hours=args.window)
    before_start = cutoff - window
    after_end = cutoff + window

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not public_key or not secret_key:
        raise SystemExit("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set.")

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    print("=" * 100)
    print("LANGFUSE PRE/POST DIFF")
    print("=" * 100)
    print(f"Cutoff (UTC)   : {cutoff.isoformat()}")
    print(f"Window         : {args.window:g}h on each side")
    print(f"Before range   : [{before_start.isoformat()}, {cutoff.isoformat()})")
    print(f"After range    : [{cutoff.isoformat()}, {after_end.isoformat()})")
    print(f"Nodes          : {', '.join(NODE_NAMES)}")
    print(f"Langfuse host  : {host}")

    per_node_before: dict[str, dict] = {}
    per_node_after: dict[str, dict] = {}
    raw_before: dict[str, list] = {}
    raw_after: dict[str, list] = {}

    print("\nFetching all GENERATION observations once per window ...", flush=True)
    before_gens = fetch_all_generations(client, before_start, cutoff)
    after_gens = fetch_all_generations(client, cutoff, after_end)
    print(f"  before window: {len(before_gens)} generations")
    print(f"  after window:  {len(after_gens)} generations")
    before_gen_index = index_generations_by_parent(before_gens)
    after_gen_index = index_generations_by_parent(after_gens)

    for node in NODE_NAMES:
        print(f"\nFetching {node} chain observations ...", flush=True)
        before_obs = fetch_observations(client, node, before_start, cutoff)
        after_obs = fetch_observations(client, node, cutoff, after_end)
        print(f"  before: {len(before_obs)} chains | after: {len(after_obs)} chains")
        before_metrics = build_per_call_metrics(before_obs, before_gen_index)
        after_metrics = build_per_call_metrics(after_obs, after_gen_index)
        per_node_before[node] = summarize(before_metrics)
        per_node_after[node] = summarize(after_metrics)
        raw_before[node] = before_metrics
        raw_after[node] = after_metrics

    for node in NODE_NAMES:
        print_node_block(node, per_node_before[node], per_node_after[node])

    print_totals(per_node_before, per_node_after)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"langfuse_diff_{timestamp}.json"
    payload = {
        "generated_utc": timestamp,
        "cutoff_utc": cutoff.isoformat(),
        "window_hours": args.window,
        "before_range": [before_start.isoformat(), cutoff.isoformat()],
        "after_range": [cutoff.isoformat(), after_end.isoformat()],
        "nodes": NODE_NAMES,
        "pricing_fallback": {
            "input_per_mtok": PRICE_INPUT_PER_MTOK,
            "output_per_mtok": PRICE_OUTPUT_PER_MTOK,
        },
        "summary_before": per_node_before,
        "summary_after": per_node_after,
        "raw_before": raw_before,
        "raw_after": raw_after,
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
    print(f"\nWrote raw results to {out_path}")


if __name__ == "__main__":
    main()
