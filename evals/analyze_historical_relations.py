"""Stage 1 — analyze historical extract_relations traces from Langfuse.

Tests the hypothesis: the historical 48 output-token mean reflects thin entries
(few entities → little JSON to emit), not the thinking_budget setting.

Loads trace IDs from the 30-day Langfuse diff, fetches each trace's
extract_relations chain observation, parses entity_count and text length from
the chain input, and correlates them with the recorded output_tokens.

Run: python -m evals.analyze_historical_relations
"""
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

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


DIFF_JSON = (
    Path(__file__).resolve().parent
    / "results"
    / "langfuse_diff_30day_20260523T131405Z.json"
)


def pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx = statistics.mean(x)
    my = statistics.mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = sum((xi - mx) ** 2 for xi in x)
    dy = sum((yi - my) ** 2 for yi in y)
    if dx == 0 or dy == 0:
        return 0.0
    return num / ((dx ** 0.5) * (dy ** 0.5))


def parse_chain_input(raw_input) -> tuple[int, int, list]:
    """Pull (entity_count, cleaned_text_len, core_entities) from a chain's input.

    Langfuse stores `input` either as a JSON string or a dict, depending on
    the integration. Tolerate both.
    """
    payload = raw_input
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return 0, 0, []
    if not isinstance(payload, dict):
        return 0, 0, []
    core = payload.get("core_entities") or []
    if not isinstance(core, list):
        core = []
    cleaned = payload.get("cleaned_text") or payload.get("raw_text") or ""
    if not isinstance(cleaned, str):
        cleaned = str(cleaned)
    return len(core), len(cleaned), core


def bucket_for(entity_count: int) -> str:
    if entity_count <= 1:
        return "1"
    if entity_count == 2:
        return "2"
    if entity_count == 3:
        return "3"
    if entity_count in (4, 5):
        return "4-5"
    return "6+"


BUCKET_ORDER = ["1", "2", "3", "4-5", "6+"]


def main() -> None:
    if not DIFF_JSON.exists():
        raise SystemExit(f"Diff JSON not found: {DIFF_JSON}")
    diff = json.loads(DIFF_JSON.read_text(encoding="utf-8"))
    before_records = diff["raw_before"].get("extract_relations", [])
    if not before_records:
        raise SystemExit("No extract_relations chains in the 30-day diff before-window.")

    print("=" * 110)
    print("STAGE 1 — historical extract_relations entity-density analysis")
    print("=" * 110)
    print(f"Diff JSON     : {DIFF_JSON.name}")
    print(f"Chains loaded : {len(before_records)}")

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not public_key or not secret_key:
        raise SystemExit("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set.")
    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    print("\nFetching trace input from Langfuse (one trace per record)...", flush=True)

    per_trace = []
    seen_traces: dict[str, dict] = {}  # cache: a trace may contain multiple chains
    for idx, rec in enumerate(before_records, start=1):
        trace_id = rec.get("trace_id")
        chain_id = rec.get("chain_id")
        output_tokens = int(rec.get("output_tokens") or 0)
        if not trace_id or not chain_id:
            continue

        if trace_id not in seen_traces:
            try:
                trace = client.api.trace.get(trace_id=trace_id)
                seen_traces[trace_id] = trace
            except Exception as exc:
                print(f"  [{idx}/{len(before_records)}] {trace_id[:8]}... fetch failed: {exc}")
                continue
        trace = seen_traces[trace_id]

        chain_input = None
        for obs in trace.observations or []:
            if getattr(obs, "id", None) == chain_id:
                chain_input = getattr(obs, "input", None)
                break

        if chain_input is None:
            # Fall back: the trace's top-level input also carries core_entities.
            chain_input = getattr(trace, "input", None)

        entity_count, text_len, entities = parse_chain_input(chain_input)
        per_trace.append({
            "trace_id": trace_id,
            "chain_id": chain_id,
            "entity_count": entity_count,
            "text_len_chars": text_len,
            "output_tokens": output_tokens,
            "entity_names": [e.get("name") for e in entities if isinstance(e, dict)][:10],
        })
        if idx % 5 == 0:
            print(f"  fetched {idx}/{len(before_records)} ...", flush=True)

    print(f"\nResolved {len(per_trace)} chains with input data.\n")

    # ---- Per-trace table, sorted by entity_count ascending ----
    print("--- Per-trace (sorted by entity_count) ---")
    header = (
        f"{'trace_id':>10} | {'entity_cnt':>10} | "
        f"{'text_len':>9} | {'output_toks':>11}"
    )
    print(header)
    print("-" * len(header))
    for row in sorted(per_trace, key=lambda r: (r["entity_count"], r["text_len_chars"])):
        print(
            f"...{row['trace_id'][-8:]:>7} | "
            f"{row['entity_count']:>10} | "
            f"{row['text_len_chars']:>9} | "
            f"{row['output_tokens']:>11}"
        )

    # ---- Histogram ----
    counts = Counter(r["entity_count"] for r in per_trace)
    print("\n--- Entity-count histogram ---")
    for ec in sorted(counts.keys()):
        bar = "#" * counts[ec]
        print(f"  entity_count={ec:>3} : {counts[ec]:>3}  {bar}")

    # ---- Correlation ----
    ec = [r["entity_count"] for r in per_trace]
    ot = [r["output_tokens"] for r in per_trace]
    r_value = pearson(ec, ot) if len(per_trace) >= 2 else 0.0
    print(f"\nPearson r (entity_count vs output_tokens) : {r_value:+.3f}")
    r_text_len = pearson([r["text_len_chars"] for r in per_trace], ot) if len(per_trace) >= 2 else 0.0
    print(f"Pearson r (text_len_chars vs output_tokens) : {r_text_len:+.3f}")

    # ---- Bucketed means ----
    print("\n--- Mean output_tokens by entity_count bucket ---")
    by_bucket: dict[str, list[int]] = {b: [] for b in BUCKET_ORDER}
    for r in per_trace:
        by_bucket[bucket_for(r["entity_count"])].append(r["output_tokens"])
    bucket_means: dict[str, float] = {}
    header2 = f"{'bucket':>8} | {'n':>4} | {'mean_out_toks':>14} | {'stddev':>9} | {'median':>7}"
    print(header2)
    print("-" * len(header2))
    for b in BUCKET_ORDER:
        vals = by_bucket[b]
        if not vals:
            print(f"{b:>8} | {0:>4} | {'—':>14} | {'—':>9} | {'—':>7}")
            bucket_means[b] = float("nan")
            continue
        m = statistics.mean(vals)
        s = statistics.stdev(vals) if len(vals) > 1 else 0.0
        med = statistics.median(vals)
        bucket_means[b] = m
        print(f"{b:>8} | {len(vals):>4} | {m:>14.1f} | {s:>9.1f} | {med:>7.1f}")

    # ---- Verdict ----
    print("\n--- VERDICT ---")
    # Mean output_tokens for entity_count <= 3
    low_density = [r["output_tokens"] for r in per_trace if r["entity_count"] <= 3]
    high_density = [r["output_tokens"] for r in per_trace if r["entity_count"] >= 5]
    low_mean = statistics.mean(low_density) if low_density else None
    high_mean = statistics.mean(high_density) if high_density else None

    print(f"  n(entity_count <= 3) = {len(low_density)}, mean output_tokens = "
          f"{low_mean:.1f}" if low_mean is not None else
          f"  n(entity_count <= 3) = 0 (no data)")
    print(f"  n(entity_count >= 5) = {len(high_density)}, mean output_tokens = "
          f"{high_mean:.1f}" if high_mean is not None else
          f"  n(entity_count >= 5) = 0 (no data)")

    confirmed = (
        low_mean is not None
        and high_mean is not None
        and low_mean < 60
        and high_mean > 150
    )
    if confirmed:
        verdict = (
            "CONFIRMED: historical 48 explained by entity sparsity "
            "(low-density mean < 60 AND high-density mean > 150)."
        )
    else:
        # Be explicit about which arm failed.
        reasons = []
        if low_mean is None:
            reasons.append("no traces with entity_count <= 3")
        elif low_mean >= 60:
            reasons.append(f"low-density mean = {low_mean:.1f} (>= 60)")
        if high_mean is None:
            reasons.append("no traces with entity_count >= 5")
        elif high_mean <= 150:
            reasons.append(f"high-density mean = {high_mean:.1f} (<= 150)")
        verdict = (
            "INCONCLUSIVE: entity count alone does not explain the 48-token baseline "
            f"({'; '.join(reasons)})."
        )
    print(f"  {verdict}")

    # ---- Persist ----
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = diff.get("generated_utc", "manual")
    out_path = out_dir / f"analyze_historical_relations_{timestamp}.json"
    payload = {
        "source_diff": DIFF_JSON.name,
        "n_chains_loaded": len(before_records),
        "n_chains_resolved": len(per_trace),
        "per_trace": per_trace,
        "histogram": dict(sorted(counts.items())),
        "pearson_entity_vs_output": r_value,
        "pearson_textlen_vs_output": r_text_len,
        "bucket_means": bucket_means,
        "low_density_mean": low_mean,
        "high_density_mean": high_mean,
        "confirmed": confirmed,
        "verdict": verdict,
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
    print(f"\nWrote results to {out_path}")


if __name__ == "__main__":
    main()
