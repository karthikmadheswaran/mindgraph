"""Diff two eval runs: summary metric deltas + per-case pass/fail flips.

Usage:
    python evals/compare.py <baseline.json> <candidate.json>
    python evals/compare.py --latest ask_retrieval_eval        # two newest runs
    python evals/compare.py --harness ask_retrieval_eval --sha 23e95fa --sha d01ee80

Works against the evals/results/ convention (see evals/provenance.py):
case identity = "question" or "case_id"; pass signal = "hit" or "passed".
Exit code 1 when the candidate has regressions (pass -> fail flips), so this
can gate scripts. (ADR-0001 Phase 5 / former Known-Broken P2 item.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from provenance import find_runs, load_run  # noqa: E402


def _case_key(case: dict) -> str:
    return str(case.get("question") or case.get("case_id") or case.get("name") or "?")


def _passed(case: dict):
    for key in ("hit", "passed", "pass"):
        if key in case:
            return bool(case[key])
    return None


def _index(run: dict) -> dict:
    return {_case_key(c): c for c in run.get("results", [])}


def _fmt(v):
    return f"{v:.3f}" if isinstance(v, float) else str(v)


def compare(baseline: dict, candidate: dict) -> int:
    b_meta, c_meta = baseline.get("metadata", {}), candidate.get("metadata", {})
    print(f"baseline : {b_meta.get('git_commit', '?')[:8]}  {b_meta.get('ran_at', '?')}")
    print(f"candidate: {c_meta.get('git_commit', '?')[:8]}  {c_meta.get('ran_at', '?')}")

    print("\n== summary deltas ==")
    b_sum, c_sum = baseline.get("summary", {}), candidate.get("summary", {})
    for key in sorted(set(b_sum) | set(c_sum)):
        b, c = b_sum.get(key), c_sum.get(key)
        if isinstance(b, (int, float)) and isinstance(c, (int, float)) and b != c:
            arrow = "▲" if c > b else "▼"
            print(f"  {key:<28} {_fmt(b)} -> {_fmt(c)}  {arrow}")

    b_cases, c_cases = _index(baseline), _index(candidate)
    regressions, fixes = [], []
    for key in sorted(set(b_cases) & set(c_cases)):
        b_pass, c_pass = _passed(b_cases[key]), _passed(c_cases[key])
        if b_pass is None or c_pass is None or b_pass == c_pass:
            continue
        (fixes if c_pass else regressions).append(key)

    print(f"\n== per-case flips ({len(set(b_cases) & set(c_cases))} shared cases) ==")
    for key in fixes:
        print(f"  FIXED      {key[:90]}")
    for key in regressions:
        print(f"  REGRESSED  {key[:90]}")
    if not fixes and not regressions:
        print("  none")

    only_b = set(b_cases) - set(c_cases)
    only_c = set(c_cases) - set(b_cases)
    if only_b or only_c:
        print(f"\n  cases only in baseline: {len(only_b)} · only in candidate: {len(only_c)}")

    return 1 if regressions else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="baseline.json candidate.json")
    ap.add_argument("--latest", metavar="HARNESS", help="diff the two newest runs of a harness prefix")
    ap.add_argument("--harness", help="harness prefix for --sha lookup")
    ap.add_argument("--sha", action="append", default=[], help="pick run by commit SHA prefix (twice)")
    args = ap.parse_args()

    if args.latest:
        runs = find_runs(args.latest)
        if len(runs) < 2:
            ap.error(f"need >=2 runs of {args.latest!r}, found {len(runs)}")
        paths = runs[-2:]
    elif args.harness and len(args.sha) == 2:
        paths = []
        for sha in args.sha:
            matches = [p for p in find_runs(args.harness)
                       if load_run(p).get("metadata", {}).get("git_commit", "").startswith(sha)]
            if not matches:
                ap.error(f"no {args.harness!r} run for SHA {sha!r}")
            paths.append(matches[-1])
    elif len(args.files) == 2:
        paths = [Path(f) for f in args.files]
    else:
        ap.error("pass two files, or --latest HARNESS, or --harness H --sha A --sha B")

    print(f"comparing:\n  {paths[0]}\n  {paths[1]}\n")
    return compare(load_run(paths[0]), load_run(paths[1]))


if __name__ == "__main__":
    sys.exit(main())
