"""Throwaway: complete the judgment of an infra-errored case from its SAVED
transcript, through the harness's own judge_case (same judge model, prompt,
backoff, overlap computation). Patches the results JSON in place and recomputes
summary/breakdown. Use: python evals/_rejudge_case.py <results.json> <scenario> <persona>
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))         # evals/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

import eval_ask_multiturn as h  # noqa: E402  (harness bootstraps the rest)
from scenarios import SCENARIOS  # noqa: E402


async def main(path: Path, scenario_id: str, persona: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    case = next(
        c for c in data["per_case"]
        if c["scenario"] == scenario_id and c["persona"] == persona
    )
    assert case.get("passed") is None and case.get("transcript"), "not an unjudged errored case"
    scenario = next(s for s in SCENARIOS if s.id == scenario_id)

    transcript = case["transcript"]
    verdict = await h.judge_case(scenario, persona, transcript)
    case["passed"] = verdict["passed"]
    case["judge_reason"] = verdict["judge_reason"]
    case["jaccard_overlap"] = verdict["jaccard_overlap"]
    case["error"] = None
    case["offline_rejudge_note"] = (
        "Judge call 429-failed in-run AND in the salvage pass (quota trough); "
        "re-judged offline from the saved transcript via the identical "
        "judge_case path. Generation transcript untouched."
    )

    # Recompute affected breakdown rows from per_case (an errored case may be
    # entirely ABSENT from the original aggregation — create rows as needed).
    results = data["per_case"]
    judged = [c for c in results if c.get("passed") is not None]
    data["summary"]["passed"] = sum(1 for c in judged if c["passed"])
    sc = data["breakdown"]["per_scenario"].setdefault(scenario_id, {})
    sc["passed"] = sum(1 for c in judged if c["scenario"] == scenario_id and c["passed"])
    sc["total"] = sum(1 for c in judged if c["scenario"] == scenario_id)
    pp = data["breakdown"]["per_persona"].setdefault(persona, {})
    pp["passed"] = sum(1 for c in judged if c["persona"] == persona and c["passed"])
    pp["total"] = sum(1 for c in judged if c["persona"] == persona)
    data["breakdown"]["errored"] = sum(1 for c in results if c.get("passed") is None)
    if scenario_id == "reask_loop":
        data["breakdown"]["reask_loop_by_persona"][persona] = (
            "PASS" if verdict["passed"] else "FAIL"
        )

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"re-judged {scenario_id}/{persona}: passed={verdict['passed']} "
          f"overlap={verdict['jaccard_overlap']}")
    print(f"reason: {verdict['judge_reason'][:200]}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2], sys.argv[3]))
