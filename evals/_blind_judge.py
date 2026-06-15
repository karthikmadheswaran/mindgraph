"""Blind batch-judging tooling for the 11/06 amended protocol (agent judge).

prep:    extract case-runs from results JSONs, strip ALL config-identifying
         fields (model, thinking, latency, tokens, overlap), shuffle with a
         recorded seed, write:
           - evals/results/blind_bundle.json   (transcripts only — the judge reads this)
           - evals/results/blind_mapping.json  (blind_id -> source; NOT read until verdicts exist)
unblind: join a verdicts JSON (written by the judge) with the mapping +
         source overlaps, aggregate per run and per config, write a
         SHA-stamped judged-results JSON to evals/results/.

Usage:
  python evals/_blind_judge.py prep <results1.json> <results2.json> ...
  python evals/_blind_judge.py unblind <verdicts.json> <out_label>
"""
import json
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
BUNDLE = RESULTS / "blind_bundle.json"
MAPPING = RESULTS / "blind_mapping.json"
SEED = 20260611

RUBRIC = {
    "categories": ["verbatim_redump", "cosmetic_ack_redump", "partial_transform", "full_transform"],
    "rules": [
        "A trailing engagement question must NOT affect the verdict in either direction.",
        "PASS requires the substance of t2 to be re-presented differently from t1 "
        "(different structure, ordering, granularity, or a clarifying pivot).",
        "An acknowledgment prefix on the same list is cosmetic_ack_redump = FAIL.",
    ],
    "verdict_schema": "{case_id, quoted_t2_evidence, redump_or_transform, pass, score_1_5, rationale}",
}


def prep(paths: list[str]) -> None:
    items, mapping = [], {}
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for case in data["per_case"]:
            key = f"{Path(path).name}::{case['scenario']}::{case['persona']}"
            transcript = [
                {"turn": t["turn"], "role": t["role"], "content": t["content"]}
                for t in case.get("transcript", [])
            ]
            if not transcript:
                print(f"SKIP (no transcript): {key}")
                continue
            items.append({"key": key, "probe_turn": case.get("probe_turn"), "transcript": transcript})
            mapping[key] = {
                "source_file": Path(path).name,
                "scenario": case["scenario"],
                "persona": case["persona"],
                "jaccard_overlap": case.get("jaccard_overlap"),
                "run_config": data.get("run_config", {}),
            }
    rng = random.Random(SEED)
    rng.shuffle(items)
    blind, blind_map = [], {}
    for i, it in enumerate(items, 1):
        bid = f"case_{i:03d}"
        blind.append({"case_id": bid, "probe_turn": it["probe_turn"], "transcript": it["transcript"]})
        blind_map[bid] = mapping[it["key"]]
    BUNDLE.write_text(
        json.dumps({"seed": SEED, "rubric": RUBRIC, "cases": blind}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    MAPPING.write_text(json.dumps(blind_map, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"prepped {len(blind)} blind case-runs -> {BUNDLE.name}, mapping -> {MAPPING.name}")


def unblind(verdicts_path: str, label: str) -> None:
    verdicts = json.loads(Path(verdicts_path).read_text(encoding="utf-8"))
    blind_map = json.loads(MAPPING.read_text(encoding="utf-8"))
    joined = []
    for v in verdicts:
        src = blind_map[v["case_id"]]
        joined.append({**v, **src})

    # Aggregate per source run, then per config (model+thinking).
    per_run: dict[str, dict] = {}
    for j in joined:
        r = per_run.setdefault(j["source_file"], {"scores": [], "passes": 0, "n": 0, "overlaps": [],
                                                  "config": f"{j['run_config'].get('ask_generation_model','?')} / {j['run_config'].get('ask_generation_thinking','') or 'budget0'}"})
        r["scores"].append(j["score_1_5"])
        r["passes"] += bool(j["pass"])
        r["n"] += 1
        if j.get("jaccard_overlap") is not None:
            r["overlaps"].append(j["jaccard_overlap"])

    per_config: dict[str, dict] = {}
    for run, r in per_run.items():
        c = per_config.setdefault(r["config"], {"run_means": [], "passes": 0, "n": 0, "overlaps": []})
        c["run_means"].append(round(sum(r["scores"]) / len(r["scores"]), 2))
        c["passes"] += r["passes"]
        c["n"] += r["n"]
        c["overlaps"].extend(r["overlaps"])
    for c in per_config.values():
        c["mean_score"] = round(sum(c["run_means"]) / len(c["run_means"]), 2)
        c["min_run_mean"] = min(c["run_means"])
        c["mean_overlap"] = round(sum(c["overlaps"]) / len(c["overlaps"]), 3) if c["overlaps"] else None

    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(HERE.parent)).strip()
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out = RESULTS / f"blindjudge_{label}_{sha[:12]}_{ts}.json"
    out.write_text(json.dumps({
        "commit_sha": sha,
        "timestamp": ts,
        "judge": "session-agent batch (blind), per 11/06 amended protocol",
        "judge_note": (
            "Blinding limitation: the session agent had previously seen a handful of "
            "these transcripts attributed (4 A case-runs, 1 B case-run) during earlier "
            "analysis; shuffle seed + rubric quotes keep verdicts auditable."
        ),
        "rubric": RUBRIC,
        "blind_seed": SEED,
        "per_case": joined,
        "per_run": {k: {**v, "mean_score": round(sum(v["scores"]) / len(v["scores"]), 2)} for k, v in per_run.items()},
        "per_config": per_config,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"unblinded -> {out.name}")
    for cfg, c in per_config.items():
        print(f"  {cfg}: run_means={c['run_means']} mean={c['mean_score']} "
              f"passes={c['passes']}/{c['n']} mean_overlap={c['mean_overlap']}")


if __name__ == "__main__":
    if sys.argv[1] == "prep":
        prep(sys.argv[2:])
    elif sys.argv[1] == "unblind":
        unblind(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("mode must be prep|unblind")
