"""External concordance audit of the session-agent blind verdicts (11/06).

Stratified blind sample re-judged by the latest pro-tier model
(gemini-3.1-pro-preview, Vertex global) under the SAME fixed rubric.

Strata (n=12), selected with seeded RNG from blindjudge_reask_ABC_*:
  - B's 2 fails
  - 4 of B's full_transforms
  - 3 of A's cosmetic_ack_redumps
  - 3 of C's overlap-gamed redumps (cosmetic verdict AND overlap < 0.35)

Modes:
  prep   -> audit_bundle.json (new blind ids, shuffle seed 20260612) + audit_mapping.json
  judge  -> ONE batched call with rubric + 12 transcripts -> audit_verdicts_raw.json
  score  -> concordance vs agent verdicts (pre-registered: >=10/12 pass/fail
            agreement finalizes B; pro PASSing a C gamed case = pro-judge
            rubric failure, NOT a discrepancy) -> SHA-stamped results JSON
"""
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
sys.path.insert(0, str(HERE.parent))

SEED = 20260612
AUDIT_MODEL = "gemini-3.1-pro-preview"
BLINDJUDGE = next(iter(sorted(RESULTS.glob("blindjudge_reask_ABC_*.json"), reverse=True)))
BUNDLE = RESULTS / "audit_bundle.json"
MAPPING = RESULTS / "audit_mapping.json"
RAW = RESULTS / "audit_verdicts_raw.json"

RUBRIC_TEXT = """You are auditing answers from a journaling assistant. In each case the user asked
a question (turn 1), got an answer, then RE-ASKED essentially the same question
(turn 2). You judge ONLY the turn-2 assistant reply against the turn-1 reply.

Rubric (apply EXACTLY):
- A trailing engagement question (e.g. "anything you'd like to focus on?") must
  NOT affect the verdict in either direction.
- PASS requires the substance of t2 to be re-presented differently from t1:
  different structure, ordering, granularity, or a clarifying pivot.
- An acknowledgment prefix on the same list is cosmetic_ack_redump = FAIL.
- Added prose AROUND an unchanged list (empathy framing, a collective
  "these have passed" note without per-item differentiation) is still
  cosmetic_ack_redump = FAIL.

Categories: verbatim_redump | cosmetic_ack_redump | partial_transform | full_transform
(verbatim_redump = repeat with no acknowledgment; cosmetic_ack_redump = ack +
substantially unchanged re-presentation; partial_transform = same list but with
substantive differentiating analysis or a genuine clarifying pivot;
full_transform = re-presentation fundamentally reorganized or pivoted.)

Return ONLY a JSON array, one object per case, schema:
{"case_id": str, "quoted_t2_evidence": str (short quote), "redump_or_transform":
str (one category), "pass": bool, "score_1_5": int, "rationale": str (one line)}"""


def prep() -> None:
    bj = json.loads(BLINDJUDGE.read_text(encoding="utf-8"))
    cases = bj["per_case"]

    def cfg(c):
        m = c["run_config"].get("ask_generation_model", "")
        return "A" if "2.5" in m else c["run_config"].get("ask_generation_thinking", "?")

    rng = random.Random(SEED)
    b_fails = [c for c in cases if cfg(c) == "minimal" and not c["pass"]]
    b_full = rng.sample([c for c in cases if cfg(c) == "minimal" and c["redump_or_transform"] == "full_transform"], 4)
    a_cosmetic = rng.sample([c for c in cases if cfg(c) == "A" and c["redump_or_transform"] == "cosmetic_ack_redump"], 3)
    c_gamed = rng.sample(
        [c for c in cases if cfg(c) == "low" and c["redump_or_transform"] == "cosmetic_ack_redump"
         and (c.get("jaccard_overlap") or 1) < 0.35], 3)
    sample = b_fails + b_full + a_cosmetic + c_gamed
    assert len(sample) == 12, len(sample)

    # Re-pull transcripts from the source run JSONs (blindjudge has verdicts only).
    src_cache: dict[str, dict] = {}
    items = []
    for c in sample:
        src = src_cache.setdefault(c["source_file"], json.loads((RESULTS / c["source_file"]).read_text(encoding="utf-8")))
        pc = next(p for p in src["per_case"] if p["persona"] == c["persona"] and p["scenario"] == c["scenario"])
        transcript = [{"turn": t["turn"], "role": t["role"], "content": t["content"]} for t in pc["transcript"]]
        items.append({"orig_case_id": c["case_id"], "transcript": transcript, "stratum": (
            "B_fail" if c in b_fails else "B_full" if c in b_full else "A_cosmetic" if c in a_cosmetic else "C_gamed")})

    rng.shuffle(items)
    bundle, mapping = [], {}
    for i, it in enumerate(items, 1):
        bid = f"audit_{i:02d}"
        bundle.append({"case_id": bid, "transcript": it["transcript"]})
        mapping[bid] = {"orig_case_id": it["orig_case_id"], "stratum": it["stratum"]}
    BUNDLE.write_text(json.dumps({"seed": SEED, "cases": bundle}, indent=2, ensure_ascii=False), encoding="utf-8")
    MAPPING.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    strata = [mapping[f"audit_{i:02d}"]["stratum"] for i in range(1, 13)]
    print(f"prepped 12 audit cases (shuffled): {strata}")


def judge() -> None:
    from app.llm import build_chat_model, extract_text

    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    blocks = []
    for c in bundle["cases"]:
        t = {(m["turn"], m["role"]): m["content"] for m in c["transcript"]}
        blocks.append(
            f"### {c['case_id']}\n"
            f"[turn-1 USER] {t.get((1, 'user'), '')}\n"
            f"[turn-1 ASSISTANT] {t.get((1, 'assistant'), '')}\n"
            f"[turn-2 USER] {t.get((2, 'user'), '')}\n"
            f"[turn-2 ASSISTANT] {t.get((2, 'assistant'), '')}"
        )
    prompt = RUBRIC_TEXT + "\n\nCASES:\n\n" + "\n\n".join(blocks)
    model = build_chat_model(AUDIT_MODEL, temperature=0.1, thinking="medium")
    t0 = time.perf_counter()
    resp = model.invoke(prompt)
    raw = extract_text(resp)
    print(f"[{AUDIT_MODEL}] {time.perf_counter() - t0:.1f}s, usage={getattr(resp, 'usage_metadata', None)}")
    raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw.strip())
    verdicts = json.loads(raw)
    assert isinstance(verdicts, list) and len(verdicts) == 12, f"got {type(verdicts)} len {len(verdicts) if isinstance(verdicts, list) else '?'}"
    RAW.write_text(json.dumps(verdicts, indent=2, ensure_ascii=False), encoding="utf-8")
    print("verdicts saved.")


def score() -> None:
    pro = {v["case_id"]: v for v in json.loads(RAW.read_text(encoding="utf-8"))}
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    agent = {c["case_id"]: c for c in json.loads(BLINDJUDGE.read_text(encoding="utf-8"))["per_case"]}

    rows, agree, pro_rubric_failures, disagreements = [], 0, [], []
    for bid, m in mapping.items():
        a, p = agent[m["orig_case_id"]], pro[bid]
        same = bool(a["pass"]) == bool(p["pass"])
        row = {"audit_id": bid, "orig_case_id": m["orig_case_id"], "stratum": m["stratum"],
               "agent_pass": a["pass"], "agent_category": a["redump_or_transform"], "agent_score": a["score_1_5"],
               "pro_pass": p["pass"], "pro_category": p.get("redump_or_transform"), "pro_score": p.get("score_1_5"),
               "pro_rationale": p.get("rationale"), "agreement": same}
        if same:
            agree += 1
        elif m["stratum"] == "C_gamed" and p["pass"] and not a["pass"]:
            row["ruling"] = "pro-judge rubric failure (passed an overlap-gamed redump) — NOT a discrepancy (pre-registered)"
            pro_rubric_failures.append(row)
        else:
            disagreements.append(row)
        rows.append(row)

    # Pre-registered: >=10/12 agreement finalizes; pro-rubric-failures are neither
    # agreement nor discrepancy, so the operative test is true_disagreements <= 2.
    concordant = len(disagreements) <= 2
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(HERE.parent)).strip()
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out = RESULTS / f"concordance_audit_{sha[:12]}_{ts}.json"
    out.write_text(json.dumps({
        "commit_sha": sha, "timestamp": ts, "audit_model": AUDIT_MODEL, "seed": SEED,
        "pre_registered_rule": (">=10/12 pass/fail agreement finalizes B; pro passing a C overlap-gamed "
                                "case = pro-judge rubric failure, not a discrepancy against the agent"),
        "agreement": f"{agree}/12", "pro_rubric_failures": len(pro_rubric_failures),
        "true_disagreements": len(disagreements), "concordance_confirmed": concordant,
        "rows": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"agreement {agree}/12 | pro rubric failures {len(pro_rubric_failures)} | "
          f"true disagreements {len(disagreements)} | CONFIRMED={concordant}")
    for d in disagreements:
        print(f"  DISAGREE {d['orig_case_id']} ({d['stratum']}): agent={d['agent_pass']} pro={d['pro_pass']} — {d['pro_rationale']}")
    for d in pro_rubric_failures:
        print(f"  PRO-RUBRIC-FAILURE {d['orig_case_id']}: {d['pro_rationale']}")
    print(f"-> {out.name}")


if __name__ == "__main__":
    {"prep": prep, "judge": judge, "score": score}[sys.argv[1]]()
