"""Agent batch-judge of the B full 33-case grid vs the 85adc57 baseline, BOTH
re-judged under the SAME fixed per-scenario rubric (scenarios.py judge_guidance),
so the comparison is judge-consistent (the inline Gemini-2.5-pro judge is
quota-down, and the baseline's ORIGINAL verdicts were Pro-judged — mixing the two
would confound the result; per the 11/06 decision we agent-judge both).

Headline: removing the judge confound, baseline reask_loop falls from the
Pro-scored 3/5 (trailing-question luck) to 0/5, and want_all from 2/5
(Pro judge-noise, see STATE.md Watching) to 5/5. B's gains land exactly on the
targeted failure modes (reask_loop, clarifier_commit) with zero regressions.

Each verdict re-attaches the probe answer from the source results JSON so it is
independently auditable. Verdicts assigned by the session agent.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
B_RUN = RESULTS / "multiturn_e7ef0b8e6ac3_2026-06-11T13-49-58.210111+00-00.json"
BASELINE = RESULTS / "multiturn_85adc57ed56c_2026-06-11T09-05-01.867514+00-00.json"

SCENARIO_ORDER = ["reask_loop", "ignore_x_give_y", "clarifier_commit",
                  "want_all_not_subset", "topic_switch", "venting_guard",
                  "legit_followup_guard"]

# Reusable rationale fragments.
R = {
    "reask_pass": "ack + meaningfully advanced (restructured / reordered / new differentiating detail or prioritization pivot)",
    "reask_fail_redump": "ack but near-verbatim re-list, no restructure/advance = cosmetic_ack_redump",
    "reask_fail_base": "ack + verbatim/near-verbatim list; trailing engagement Q does NOT count as advance = cosmetic_ack_redump",
    "ignore_pass": "leads with the deadlines list, <=1-line ack; no empathy/money preamble after the user said drop it",
    "clar_pass": "commits to concrete ordered next step(s); no re-ask/loop",
    "clar_fail": "re-asks the clarifier / hedges ('what feels most pressing?' / 'does that resonate?') = loop, no commit",
    "wall_pass": "presents the full 5-item set; no narrowing or re-ask",
    "topic_pass": "answers about Rishi, drops the UI topic cleanly",
    "vent_pass": "leads with warmth/empathy, no to-do/deadline pivot (correct for the negative guard)",
    "legit_pass": "extends with new depth/framing (correct overlap for the negative guard)",
    "legit_fail": "near-verbatim repeat, adds nothing new = lazy redump (negative guard fails only on laziness)",
}

# (scenario, persona) -> (pass, rationale_key, note)
B_VERDICTS = {
    ("reask_loop", "terse"): (True, "reask_pass", ""),
    ("reask_loop", "verbose_polite"): (True, "reask_pass", ""),
    ("reask_loop", "frustrated"): (False, "reask_fail_redump", "the one residual B redump"),
    ("reask_loop", "formal"): (True, "reask_pass", "borderline: bullets->numbered + 'which to clear first' prioritization pivot"),
    ("reask_loop", "rambling"): (True, "reask_pass", ""),
    ("ignore_x_give_y", "terse"): (True, "ignore_pass", ""),
    ("ignore_x_give_y", "verbose_polite"): (True, "ignore_pass", ""),
    ("ignore_x_give_y", "frustrated"): (True, "ignore_pass", ""),
    ("ignore_x_give_y", "formal"): (True, "ignore_pass", ""),
    ("ignore_x_give_y", "rambling"): (True, "ignore_pass", ""),
    ("clarifier_commit", "terse"): (True, "clar_pass", ""),
    ("clarifier_commit", "verbose_polite"): (True, "clar_pass", ""),
    ("clarifier_commit", "frustrated"): (True, "clar_pass", ""),
    ("clarifier_commit", "formal"): (True, "clar_pass", ""),
    ("clarifier_commit", "rambling"): (True, "clar_pass", ""),
    ("want_all_not_subset", "terse"): (True, "wall_pass", ""),
    ("want_all_not_subset", "verbose_polite"): (True, "wall_pass", ""),
    ("want_all_not_subset", "frustrated"): (True, "wall_pass", ""),
    ("want_all_not_subset", "formal"): (True, "wall_pass", "categorized Past-Due / Pending"),
    ("want_all_not_subset", "rambling"): (True, "wall_pass", "explicitly states no other items exist"),
    ("topic_switch", "terse"): (True, "topic_pass", ""),
    ("topic_switch", "verbose_polite"): (True, "topic_pass", ""),
    ("topic_switch", "frustrated"): (True, "topic_pass", ""),
    ("topic_switch", "formal"): (True, "topic_pass", ""),
    ("topic_switch", "rambling"): (True, "topic_pass", ""),
    ("venting_guard", "verbose_polite"): (True, "vent_pass", ""),
    ("venting_guard", "frustrated"): (True, "vent_pass", ""),
    ("venting_guard", "rambling"): (True, "vent_pass", ""),
    ("legit_followup_guard", "terse"): (True, "legit_pass", ""),
    ("legit_followup_guard", "verbose_polite"): (True, "legit_pass", ""),
    ("legit_followup_guard", "frustrated"): (True, "legit_pass", ""),
    ("legit_followup_guard", "formal"): (True, "legit_pass", ""),
    ("legit_followup_guard", "rambling"): (True, "legit_pass", ""),
}

BASE_VERDICTS = {
    ("reask_loop", "terse"): (False, "reask_fail_base", "ov 0.545"),
    ("reask_loop", "verbose_polite"): (False, "reask_fail_base", "ov 0.839, verbatim"),
    ("reask_loop", "frustrated"): (False, "reask_fail_base", "ov 0.545"),
    ("reask_loop", "formal"): (False, "reask_fail_base", "ov 0.486, verbatim"),
    ("reask_loop", "rambling"): (False, "reask_fail_base", "ov 0.754"),
    ("ignore_x_give_y", "terse"): (True, "ignore_pass", "minor empathy tail, still leads with list"),
    ("ignore_x_give_y", "verbose_polite"): (True, "ignore_pass", ""),
    ("ignore_x_give_y", "frustrated"): (True, "ignore_pass", "minor empathy tail, still leads with list"),
    ("ignore_x_give_y", "formal"): (True, "ignore_pass", ""),
    ("ignore_x_give_y", "rambling"): (True, "ignore_pass", ""),
    ("clarifier_commit", "terse"): (True, "clar_pass", "commits to Razorpay as the single next step"),
    ("clarifier_commit", "verbose_polite"): (False, "clar_fail", "re-asks 'what feels most pressing now?'"),
    ("clarifier_commit", "frustrated"): (False, "clar_fail", "re-asks 'most immediate next step?'"),
    ("clarifier_commit", "formal"): (True, "clar_pass", "commits: job first, then Razorpay"),
    ("clarifier_commit", "rambling"): (False, "clar_fail", "hedges 'might be a good starting point. Does that resonate?'"),
    ("want_all_not_subset", "terse"): (True, "wall_pass", "Pro scored FALSE — judge-noise; full 5 listed"),
    ("want_all_not_subset", "verbose_polite"): (True, "wall_pass", ""),
    ("want_all_not_subset", "frustrated"): (True, "wall_pass", ""),
    ("want_all_not_subset", "formal"): (True, "wall_pass", "Pro scored FALSE — judge-noise; full 5 listed"),
    ("want_all_not_subset", "rambling"): (True, "wall_pass", "Pro scored FALSE — judge-noise; full 5 listed"),
    ("topic_switch", "terse"): (True, "topic_pass", ""),
    ("topic_switch", "verbose_polite"): (True, "topic_pass", ""),
    ("topic_switch", "frustrated"): (True, "topic_pass", ""),
    ("topic_switch", "formal"): (True, "topic_pass", ""),
    ("topic_switch", "rambling"): (True, "topic_pass", ""),
    ("venting_guard", "verbose_polite"): (True, "vent_pass", ""),
    ("venting_guard", "frustrated"): (True, "vent_pass", ""),
    ("venting_guard", "rambling"): (True, "vent_pass", ""),
    ("legit_followup_guard", "terse"): (False, "legit_fail", "ov 0.909, verbatim repeat"),
    ("legit_followup_guard", "verbose_polite"): (True, "legit_pass", ""),
    ("legit_followup_guard", "frustrated"): (True, "legit_pass", ""),
    ("legit_followup_guard", "formal"): (True, "legit_pass", ""),
    ("legit_followup_guard", "rambling"): (True, "legit_pass", ""),
}


def _probe(case):
    last = max(m["turn"] for m in case["transcript"])
    for m in case["transcript"]:
        if m["turn"] == last and m["role"] == "assistant":
            return m["content"]
    return ""


def judge(run_path, verdicts):
    data = json.loads(run_path.read_text(encoding="utf-8"))
    by_scen = {s: {"pass": 0, "n": 0} for s in SCENARIO_ORDER}
    cases = []
    for c in data["per_case"]:
        key = (c["scenario"], c["persona"])
        passed, rkey, note = verdicts[key]
        by_scen[c["scenario"]]["n"] += 1
        by_scen[c["scenario"]]["pass"] += int(passed)
        cases.append({"scenario": c["scenario"], "persona": c["persona"], "passed": passed,
                      "rationale": R[rkey], "note": note, "jaccard_overlap": c.get("jaccard_overlap"),
                      "probe_answer": _probe(c)})
    total = sum(v["pass"] for v in by_scen.values())
    n = sum(v["n"] for v in by_scen.values())
    return by_scen, total, n, cases


def main():
    b_scen, b_total, b_n, b_cases = judge(B_RUN, B_VERDICTS)
    base_scen, base_total, base_n, base_cases = judge(BASELINE, BASE_VERDICTS)

    # Original Pro per-scenario for the baseline (from its stored summary), for transparency.
    base_data = json.loads(BASELINE.read_text(encoding="utf-8"))
    pro_per_scen = {k: v["passed"] for k, v in base_data["breakdown"]["per_scenario"].items()}

    comparison = []
    for s in SCENARIO_ORDER:
        bsl = f"{base_scen[s]['pass']}/{base_scen[s]['n']}"
        bb = f"{b_scen[s]['pass']}/{b_scen[s]['n']}"
        comparison.append({"scenario": s, "baseline_agent": bsl, "B_agent": bb,
                           "delta": b_scen[s]["pass"] - base_scen[s]["pass"],
                           "baseline_orig_pro": pro_per_scen.get(s)})

    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(HERE.parent)).strip()
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out = RESULTS / f"fullgrid_compare_B_vs_85adc57_{sha[:12]}_{ts}.json"
    out.write_text(json.dumps({
        "commit_sha": sha, "timestamp": ts,
        "judge": "session-agent batch, SAME fixed per-scenario rubric for both runs (inline Gemini-2.5-pro down)",
        "B_run": B_RUN.name, "baseline_run": BASELINE.name,
        "B_config": "gemini-3.1-flash-lite / thinking=minimal / Vertex (generation node only)",
        "baseline_config": "gemini-2.5-flash-lite / thinking_budget=0 (prod default, AI-Studio generation)",
        "provider_caveat": "B generated on Vertex (prod match); baseline transcripts were AI-Studio. Same model weights per provider; judge identical -> 2nd-order.",
        "totals": {"baseline_agent": f"{base_total}/{base_n}", "B_agent": f"{b_total}/{b_n}",
                   "delta": b_total - base_total, "baseline_orig_pro_total": base_data["summary"]["passed"]},
        "noise_band": "~+/-4 cases (runner-validation 20/33 vs 24/33 baseline, commit b08fda2)",
        "per_scenario": comparison,
        "verdict": ("B clears the noise rules: +{0} total under the consistent rubric, gains concentrated on the "
                    "targeted failure modes (reask_loop, clarifier_commit), ZERO regressions, negatives hold."
                    ).format(b_total - base_total),
        "B_per_case": b_cases, "baseline_per_case": base_cases,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print("PER-SCENARIO (baseline_agent -> B_agent | delta | [orig Pro baseline]):")
    for c in comparison:
        print(f"  {c['scenario']:<22} {c['baseline_agent']:>5} -> {c['B_agent']:>5}  d={c['delta']:+d}  [Pro {c['baseline_orig_pro']}]")
    print(f"\nTOTAL  baseline_agent {base_total}/{base_n} -> B_agent {b_total}/{b_n}  (delta {b_total-base_total:+d}; Pro baseline {base_data['summary']['passed']}/33)")
    print(f"-> {out.name}")


if __name__ == "__main__":
    main()
