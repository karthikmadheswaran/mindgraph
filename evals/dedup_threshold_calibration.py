"""Calibrate the entry-dedup similarity threshold against real embeddings.

WHY: the dedup node (app/nodes/dedup.py) flags a new entry as a near-duplicate
when its cosine similarity to the closest existing entry exceeds
DEDUP_SIMILARITY_THRESHOLD, routing the graph to END so the entry is never
stored/extracted. The original 0.85 cutoff false-positived on same-voice journal
prose — a real unique entry scored 0.8596 against an unrelated earlier entry and
was swallowed (empty cleaned_text/title/entities).

This harness measures, for one user's real corpus (read-only, STORED embeddings
— no embedding API calls):
  - the false-positive pair's cosine (if a target entry is given),
  - the query entry's nearest neighbours,
  - the cosine distribution over all DISTINCT entry pairs,
  - how many distinct pairs each candidate threshold would mis-flag.

It establishes that 0.92 clears the observed distinct-pair max with margin while
staying well below the true-resubmit range (~0.97-1.0).

PRIVACY: this reads real (private) journal data. No user_id, entry text, or
result file is committed — pass identifiers at runtime and keep outputs local.

Run (read-only):
    python -m evals.dedup_threshold_calibration \
        --user-id <uuid> \
        --query-trace evals/results/trace_inspect_<id>.json \
        [--false-positive-target <entry-uuid>]

--query-trace points at an inspect_langfuse_trace.py dump of the swallowed
entry's pipeline run; its normalize span carries the entry_embedding (the entry
itself has no stored embedding because store_node was skipped). Alternatively
pass --query-entry-id to use a stored embedding.
"""
import argparse
import itertools
import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

from evals.provenance import save_results

THRESHOLDS = [0.85, 0.88, 0.90, 0.92, 0.95]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _vec(row):
    e = row.get("embedding")
    return json.loads(e) if isinstance(e, str) else e


def load_query_embedding_from_trace(path: str) -> list:
    trace = json.loads(Path(path).read_text(encoding="utf-8"))
    for obs in trace["observations"]:
        if obs.get("name") == "normalize" and obs.get("type") == "CHAIN":
            return obs["output"]["entry_embedding"]
    raise SystemExit("normalize embedding not found in trace artifact")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default=os.getenv("DEDUP_CALIB_USER_ID"), required=False)
    parser.add_argument("--query-trace", help="inspect_langfuse_trace dump of the swallowed entry")
    parser.add_argument("--query-entry-id", help="use this entry's stored embedding as the query")
    parser.add_argument("--false-positive-target", help="entry the query was wrongly matched to")
    args = parser.parse_args()
    if not args.user_id:
        raise SystemExit("Pass --user-id (or set DEDUP_CALIB_USER_ID).")

    from supabase import create_client

    sb = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY"),
    )

    rows = (
        sb.table("entries")
        .select("id, created_at, auto_title, embedding")
        .eq("user_id", args.user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    corpus = [r for r in rows if r.get("embedding")]

    if args.query_trace:
        query = load_query_embedding_from_trace(args.query_trace)
    elif args.query_entry_id:
        match = next((r for r in corpus if r["id"] == args.query_entry_id), None)
        if not match:
            raise SystemExit(f"query entry {args.query_entry_id} has no stored embedding")
        query = _vec(match)
    else:
        raise SystemExit("Pass --query-trace or --query-entry-id.")

    target = next((r for r in corpus if r["id"] == args.false_positive_target), None)
    false_positive_sim = round(cosine(query, _vec(target)), 4) if target else None

    nearest = sorted(
        (
            {
                "case_id": r["id"],
                "date": r["created_at"][:10],
                "cosine": round(cosine(query, _vec(r)), 4),
            }
            for r in corpus
        ),
        key=lambda x: x["cosine"],
        reverse=True,
    )[:10]

    pair_sims = sorted(
        (cosine(_vec(a), _vec(b)) for a, b in itertools.combinations(corpus, 2)),
        reverse=True,
    )
    n = len(pair_sims)

    def pct(p):
        return round(pair_sims[min(n - 1, int(n * p))], 4) if n else None

    distinct_pairs_over = {str(t): sum(1 for s in pair_sims if s > t) for t in THRESHOLDS}

    summary = {
        "corpus_entries_with_embedding": len(corpus),
        "distinct_pairs": n,
        "false_positive_pair_cosine": false_positive_sim,
        "distinct_pair_cosine": {
            "max": pct(0.0),
            "p99": pct(0.01),
            "p95": pct(0.05),
            "median": pct(0.5),
        },
        "distinct_pairs_over_threshold": distinct_pairs_over,
        "threshold_before": 0.85,
        "threshold_after": 0.92,
    }

    # NOTE: result intentionally NOT saved by default — it embeds entry IDs from a
    # private corpus and this is a public repo. Pass --save to write locally.
    print(json.dumps(summary, indent=2))
    if os.getenv("DEDUP_CALIB_SAVE"):
        path = save_results("dedup_threshold_calibration", summary, nearest)
        print(f"\nWrote {path} (LOCAL ONLY — do not commit; contains entry IDs)")


if __name__ == "__main__":
    main()
