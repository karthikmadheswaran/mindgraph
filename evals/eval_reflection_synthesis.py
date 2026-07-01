"""
evals/eval_reflection_synthesis.py — deterministic INPUT eval for the Reflection
self-synthesis engine (app/synthesis_engine.py).

WHY deterministic / input-only (mirrors eval_ask_deadlines.py):
The VALUE of this feature — "is this a real, non-obvious revelation" — is not
machine-checkable and is deferred to human review at the Phase-1 checkpoint. What
IS deterministically checkable, and is the whole point of the rebuild, is that the
shallow-INPUT root cause is gone: the model is now fed FULL journal text and is
NOT fed the entity mention-count list. STATE also flags the CI judge as
non-reproducible, so an output-grading LLM eval would be flaky and costs credits.

So we assert on the BUILT PROMPT (the input the model receives), driving the REAL
synthesis_engine fetch+format+prompt path against an in-memory Supabase fake (same
fake shape as tests/test_deadline_soft_delete.py / eval_ask_deadlines.py). No
network, no API credit, CI-safe.

The RED->GREEN proof: the same assertions are also run against a reproduction of
the OLD engine's input format (raw_text[:200] + "N mentions" entity list). The old
format FAILS the assertions the new prompt PASSES — proving the checks have teeth
and that the input genuinely changed.

Usage:
    python -m evals.eval_reflection_synthesis      # exit 0 = GREEN, exit 1 = RED
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Env bootstrap MUST precede any app.* import (app/llm.py builds its Gemini client
# at module load from os.getenv). Dummy values are fine — the AI Studio path builds
# the client lazily and we NEVER call it (Supabase is faked, the model is not run).
# ──────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "dummy-key-no-network")
os.environ.pop("USE_VERTEX", None)  # force AI Studio import path (no ADC needed)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import app.synthesis_engine as synthesis_engine  # noqa: E402

USER = "eval-user-synthesis"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# A sentinel deliberately placed BEYOND character 200 of an entry's raw_text. If the
# built prompt contains it, the full text was included (no 200-char truncation).
SENTINEL = "SENTINEL_BEYOND_TWO_HUNDRED_CHARS_zx9"
LONG_ENTRY = ("I keep telling myself I am fine and everything is under control. " * 4
              + " " + SENTINEL + " and that last part is the honest bit.")

# Regexes for the shallow failure modes the input must NOT contain.
RE_COUNT = re.compile(r"\d+\s*(?:mentions|times)", re.IGNORECASE)   # "31 mentions", "mentioned 31 times"


# ──────────────────────────────────────────────────────────────────────────────
# In-memory Supabase PostgREST fake (mirrors eval_ask_deadlines.py; +gt operator)
# ──────────────────────────────────────────────────────────────────────────────
class FakeResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class FakeQuery:
    def __init__(self, store, table):
        self.store = store
        self.table = table
        self.filters = []
        self._limit = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    def is_(self, col, val):
        self.filters.append(("is", col, None if val == "null" else val))
        return self

    def gt(self, col, val):
        self.filters.append(("gt", col, val))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _match(self, row):
        for op, col, val in self.filters:
            cur = row.get(col)
            if op == "eq" and cur != val:
                return False
            if op == "in" and cur not in val:
                return False
            if op == "is" and cur != val:
                return False
            if op == "gt" and not (cur is not None and str(cur) > str(val)):
                return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        matched = [dict(r) for r in rows if self._match(r)]
        if self._limit is not None:
            matched = matched[: self._limit]
        return FakeResponse(matched, count=len(matched))


class FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return FakeQuery(self.store, name)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────
NOW = datetime.now(timezone.utc)


def _entry(eid, days_ago, raw_text):
    return {
        "id": eid,
        "user_id": USER,
        "raw_text": raw_text,
        "status": "completed",
        "deleted_at": None,
        "created_at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def _install_fake():
    store = {
        "entries": [
            _entry("e-1", 20, LONG_ENTRY),
            _entry("e-2", 10, "Started a brand new side project tonight instead of the tax stuff."),
            _entry("e-3", 2, "Quiet day. Didn't really want to write."),
            # noise that must be excluded from the input:
            {**_entry("e-del", 5, "deleted entry"), "deleted_at": NOW.isoformat()},
            {**_entry("e-proc", 1, "still processing"), "status": "processing"},
        ],
        "entry_tags": [
            {"entry_id": "e-1", "category": "personal"},
            {"entry_id": "e-2", "category": "work"},
            {"entry_id": "e-3", "category": "personal"},
        ],
        "user_synthesis": [],  # first run: no existing doc
    }
    synthesis_engine.supabase = FakeSupabase(store)
    return store


def _old_style_input(entries) -> str:
    """Reproduce the OLD engine's input format (insights_engine.generate_patterns):
    200-char-truncated text + an entity mention-count list. Used only to prove the
    assertions discriminate old from new — NOT part of the new path."""
    lines = [f"[{e['created_at'][:10]}] {e['raw_text'][:200]}" for e in entries]
    entity_list = "mindgraph (project, 31 mentions, last: 2026-04-14)\nlanding page (project, 4 mentions, last: 2026-04-14)"
    return "ENTRIES:\n" + "\n".join(lines) + "\n\nNOTABLE ENTITIES (mentioned 2+ times):\n" + entity_list


# ──────────────────────────────────────────────────────────────────────────────
# Checks
# ──────────────────────────────────────────────────────────────────────────────
def _run() -> tuple[list[dict], str]:
    _install_fake()
    prompt, entries = synthesis_engine.build_prompt_for_user(USER, reprocess_all=True)
    low = prompt.lower()

    # GREEN block: the NEW prompt must satisfy all of these.
    new_checks = [
        ("full raw_text included (sentinel beyond char 200 present)", SENTINEL in prompt),
        ("no occurrence-count formatting ('N mentions'/'N times')", RE_COUNT.search(prompt) is None),
        ("no entity mention_count field name injected", "mention_count" not in prompt),
        ("bounded-doc: 'draft to rewrite' instruction present", "draft to rewrite" in low),
        ("bounded-doc: 'strongest' insights cap present", "strongest" in low),
        ("distinct-from-drift guard present", "distinct from" in low or "stay in your lane" in low),
        ("completed+non-deleted entries only (3 folded, noise excluded)", len(entries) == 3),
        ("soft-deleted entry text excluded", "deleted entry" not in prompt),
        ("processing entry text excluded", "still processing" not in prompt),
    ]

    # TEETH block (RED control): the same assertions applied to the OLD input format
    # must FAIL — proving the checks actually distinguish shallow from deep input.
    old = _old_style_input([e for e in _install_fake()["entries"]
                            if e["status"] == "completed" and not e["deleted_at"]])
    teeth_checks = [
        ("old format is missing the full text (sentinel absent) — correctly caught",
         SENTINEL not in old),
        ("old format contains 'N mentions' count list — correctly caught",
         RE_COUNT.search(old) is not None),
    ]

    blocks = [
        {"id": "new_prompt", "checks": new_checks},
        {"id": "old_format_control", "checks": teeth_checks},
    ]
    failed = sum(1 for b in blocks for _, ok in b["checks"] if not ok)
    return blocks, ("GREEN" if failed == 0 else "RED")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    blocks, status = _run()
    passed = sum(1 for b in blocks for _, ok in b["checks"] if ok)
    failed = sum(1 for b in blocks for _, ok in b["checks"] if not ok)

    print("=" * 72)
    print("REFLECTION SYNTHESIS INPUT EVAL  (deterministic — asserts on built prompt)")
    print("=" * 72)
    for b in blocks:
        print(f"\n[{b['id']}]")
        for desc, ok in b["checks"]:
            print(f"   {'PASS' if ok else 'FAIL'}  {desc}")
    print("\n" + "-" * 72)
    print(f"RESULT: {status}   ({passed} passed, {failed} failed)")
    print("-" * 72)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out = RESULTS_DIR / f"reflection_synthesis_eval_{ts}.json"
    out.write_text(json.dumps({
        "metadata": {"ran_at": ts, "git_commit": _git_sha(), "user_id": USER},
        "summary": {"status": status, "passed": passed, "failed": failed},
        "blocks": [
            {"id": b["id"], "checks": [{"desc": d, "ok": ok} for d, ok in b["checks"]]}
            for b in blocks
        ],
    }, indent=2, default=str), encoding="utf-8")
    print(f"\n📁 Results: {out}")
    return 0 if status == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
