"""Throwaway aggregator for the variance-band protocol (11/06 amended Phase 2).
Reads N multiturn results JSONs (newest first by mtime, filtered to a category
subset) and prints per-run judge scores, mean, range, and t1<->t2 overlap stats.

Usage: python evals/_variance_band.py <n_runs> [category]
Not committed as harness code — the raw numbers live in the committed JSONs.
"""
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"

n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
category = sys.argv[2] if len(sys.argv) > 2 else "reask_loop"

files = sorted(
    (p for p in RESULTS.glob("multiturn_*.json")
     if json.loads(p.read_text(encoding="utf-8")).get("run_config", {}).get("category_filter") == category),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)[:n]
files.reverse()  # chronological

if len(files) < n:
    print(f"WARNING: only {len(files)} {category}-filtered runs found, wanted {n}")

scores, all_overlaps = [], []
for p in files:
    j = json.loads(p.read_text(encoding="utf-8"))
    cases = [c for c in j["per_case"] if c["scenario"] == category]
    passed = sum(1 for c in cases if c.get("passed"))
    overlaps = {c["persona"]: c.get("jaccard_overlap") for c in cases}
    ovl_vals = [v for v in overlaps.values() if v is not None]
    scores.append(passed)
    all_overlaps.extend(ovl_vals)
    cfg = j.get("run_config", {})
    print(f"{p.name}")
    print(f"  model={cfg.get('ask_generation_model','?')!r} thinking={cfg.get('ask_generation_thinking','')!r} wall={cfg.get('wall_clock_s')}s")
    print(f"  score {passed}/{len(cases)}  overlaps: " + "  ".join(f"{k}={v}" for k, v in sorted(overlaps.items())))

if scores:
    print(f"\nBAND over {len(files)} runs:")
    print(f"  judge score: per-run {scores}  mean={sum(scores)/len(scores):.2f}  range=[{min(scores)},{max(scores)}]")
    print(f"  t1<->t2 overlap: n={len(all_overlaps)}  mean={sum(all_overlaps)/len(all_overlaps):.3f}  "
          f"min={min(all_overlaps):.3f}  max={max(all_overlaps):.3f}")
