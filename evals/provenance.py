"""Eval provenance helpers (ADR-0001 Phase 5 / former Known-Broken P2 item).

Convention: every eval run writes one JSON file into evals/results/ shaped as

    {
      "metadata": {"ran_at": ISO-8601, "git_commit": full SHA, "harness": str, ...},
      "summary":  {metric_name: value, ...},
      "results":  [per-case dicts; must carry a stable identity key
                   ("question" or "case_id") and a boolean pass signal
                   ("hit" or "passed")]
    }

Files are committed to the repo, so every score is attributable to the exact
commit that produced it. Diff two runs with evals/compare.py.

New harnesses: call save_results() instead of hand-rolling json.dump.
(eval_ask_retrieval.py predates this helper and already conforms.)
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def current_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True
        ).strip()
    except Exception:
        return "unknown"


def save_results(harness: str, summary: dict, results: list, **extra_metadata) -> Path:
    """Write a SHA-stamped result file and return its path."""
    ran_at = datetime.now(timezone.utc).isoformat().replace(":", "-")
    payload = {
        "metadata": {
            "ran_at": ran_at,
            "git_commit": current_commit(),
            "harness": harness,
            **extra_metadata,
        },
        "summary": summary,
        "results": results,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{harness}_{ran_at}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load_run(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_runs(harness_prefix: str) -> list[Path]:
    """All result files for a harness prefix, oldest first (by filename timestamp)."""
    return sorted(RESULTS_DIR.glob(f"{harness_prefix}*.json"))
