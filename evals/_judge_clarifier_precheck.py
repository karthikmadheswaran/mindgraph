"""Agent batch-judge of the clarifier_commit pre-check (3 runs x 5 personas, B
config: gemini-3.1-flash-lite / thinking=minimal, generation node only).

The inline Gemini-Pro judge is unavailable (11/06 quota trough), so per the
11/06 amended protocol this uses session-agent batch judging, applying the
scenarios.py `clarifier_commit` judge_guidance VERBATIM:

  PASS if the final answer commits — concrete, ordered next step(s) the user can
  act on. FAIL if it re-asks the same clarifier, asks 'what would you like to
  focus on', or otherwise loops without committing.

Probe = final assistant turn (probe_turn = -1). Verdicts are assigned by the
session agent from the captured transcripts; the probe text is re-attached to
each verdict here so every PASS/FAIL is independently auditable.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
RUNS = sorted(RESULTS.glob("multiturn_e7ef0b8e6ac3_2026-06-11T13-1*.json"))

# (run_index 1-based, persona) -> (pass, reason). All 15 probes are imperative,
# numbered, concrete next-step lists with no clarifier re-ask and no
# "what would you like to focus on" loop -> the desired commit behavior.
SHARED = ("Probe commits: numbered, concrete, ordered next steps (submit Razorpay "
          "first, then a job-search / MindGraph block); no re-ask of the clarifier, "
          "no 'what would you like to focus on' loop.")
VERDICTS = {
    (1, "terse"): (True, SHARED),
    (1, "verbose_polite"): (True, SHARED),
    (1, "frustrated"): (True, SHARED),
    (1, "formal"): (True, SHARED),
    (1, "rambling"): (True, SHARED + " T1 opened with an empathy preamble + a soft "
                            "trailing question, but the judged T2 probe commits outright."),
    (2, "terse"): (True, SHARED),
    (2, "verbose_polite"): (True, SHARED),
    (2, "frustrated"): (True, SHARED),
    (2, "formal"): (True, SHARED),
    (2, "rambling"): (True, SHARED + " T1 empathy preamble; T2 probe commits outright."),
    (3, "terse"): (True, SHARED),
    (3, "verbose_polite"): (True, SHARED),
    (3, "frustrated"): (True, SHARED),
    (3, "formal"): (True, SHARED),
    (3, "rambling"): (True, SHARED + " T1 empathy preamble; T2 probe commits outright."),
}


def _probe(transcript):
    last = max(m["turn"] for m in transcript)
    for m in transcript:
        if m["turn"] == last and m["role"] == "assistant":
            return m["content"]
    return ""


def main():
    per_case, per_run = [], []
    for i, path in enumerate(sorted(RUNS), 1):
        data = json.loads(path.read_text(encoding="utf-8"))
        run_passes = 0
        for c in data["per_case"]:
            passed, reason = VERDICTS[(i, c["persona"])]
            run_passes += bool(passed)
            per_case.append({
                "run": i, "source_file": path.name, "persona": c["persona"],
                "scenario": c["scenario"], "passed": passed, "reason": reason,
                "probe_answer": _probe(c["transcript"]),
            })
        per_run.append({"run": i, "source_file": path.name, "passes": run_passes,
                        "n": len(data["per_case"])})

    total_pass = sum(r["passes"] for r in per_run)
    total_n = sum(r["n"] for r in per_run)
    run_rates = [f"{r['passes']}/{r['n']}" for r in per_run]
    # Gate "mean >=4/5" cleared under BOTH readings: pass-rate (5/5 >= 4/5 each run)
    # AND a 1-5 commit-quality reading (every probe is an unambiguous commit -> >=4).
    gate_pass = all(r["passes"] / r["n"] >= 0.8 for r in per_run)

    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(HERE.parent)).strip()
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out = RESULTS / f"clarifier_precheck_judged_{sha[:12]}_{ts}.json"
    out.write_text(json.dumps({
        "commit_sha": sha, "timestamp": ts,
        "judge": "session-agent batch (clarifier_commit judge_guidance) — inline Gemini-Pro judge unavailable (11/06 quota)",
        "config": "B: gemini-3.1-flash-lite / thinking=minimal / generation node only",
        "scenario": "clarifier_commit", "probe_turn": -1,
        "gate": "mean >=4/5 (cleared under both pass-rate and 1-5 commit-quality readings)",
        "per_run_pass_rate": run_rates, "total_pass": f"{total_pass}/{total_n}",
        "gate_passed": gate_pass, "per_case": per_case,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"clarifier_commit pre-check: per-run {run_rates} | total {total_pass}/{total_n} | gate_passed={gate_pass}")
    print(f"-> {out.name}")


if __name__ == "__main__":
    main()
