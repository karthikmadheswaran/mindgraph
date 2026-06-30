"""
evals/eval_ask_deadlines.py — ANSWER-CONTENT eval for deadline-list Ask queries.

WHY this exists (and why it is deterministic, not LLM-judged):
The pre-existing deadline eval case in rag_test_cases.json scores PROSE-entry
retrieval F1 — it encodes the OLD "answer deadlines from journal prose" behavior
as correct, so it cannot catch this fix and may even regress on its own terms
while the user-facing answer gets better. STATE also flags the CI re-ask judge as
non-reproducible (quota troughs) — so an LLM answer-grader would be flaky.

The bug here is STRUCTURAL, which makes a deterministic proof possible: the Ask
generation model can only mention a deadline if that deadline is in the context
it is handed. `list_deadlines(status=None)` defaults to PENDING-ONLY, so missed/
overdue deadlines are filtered out BEFORE the model ever sees them — which is
exactly why "am I behind on anything" is unanswerable. So instead of grading the
model's prose, we assert on the ASSEMBLED CONTEXT (what generation receives): if a
missed deadline is absent from the context, the model categorically cannot surface
it. This is more robust than a judge and needs no network / API credit.

It drives the REAL production nodes — app.services.ask_pipeline.dashboard_context
and context_assembler — against an in-memory fake of the Supabase PostgREST chain
(same fake shape as tests/test_deadline_soft_delete.py). dashboard_context_needed
is forced True so the CURRENT code gets its most-favorable routing; the eval still
fails pre-fix, proving the bug is the status filter, not routing.

Three query shapes (the deliverable):
  A "what's due this week"            -> PENDING deadline must appear
  B "am I behind on anything"         -> MISSED deadline must appear  (THE bug; RED pre-fix)
  C mixed "...and how have I been
     feeling about my deadlines"      -> BOTH structured deadline AND prose appear (augment)

Plus a tolerant trigger check (fix #1): if is_deadline_query exists, it must fire
True on the three deadline shapes and False on an off-topic question.

Usage:
    python -m evals.eval_ask_deadlines        # exit 0 = GREEN, exit 1 = RED
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Env bootstrap MUST precede any app.* import: app/llm.py + app/embeddings.py
# construct their Gemini clients at module load from os.getenv(...). Dummy values
# are fine — the AI Studio path constructs clients lazily and we never call them
# (Supabase is faked, generation is not run).
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

import app.services.deadline_service as deadline_service  # noqa: E402
import app.services.project_service as project_service  # noqa: E402
import app.services.ask_pipeline.context_assembler as context_assembler_mod  # noqa: E402
from app.services.ask_pipeline.context_assembler import context_assembler  # noqa: E402
from app.services.ask_pipeline.dashboard_context import dashboard_context  # noqa: E402

USER = "eval-user-deadlines"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ──────────────────────────────────────────────────────────────────────────────
# In-memory Supabase PostgREST fake (mirrors tests/test_deadline_soft_delete.py)
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
        self._mode = "select"
        self._payload = None
        self._returning = False
        self._limit = None

    def select(self, *a, **k):
        self._mode = "select"
        return self

    def update(self, data, returning=None):
        self._mode = "update"
        self._payload = data
        self._returning = returning == "representation"
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self.filters.append(("neq", col, val))
        return self

    def lt(self, col, val):
        self.filters.append(("lt", col, val))
        return self

    def gte(self, col, val):
        self.filters.append(("gte", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    def is_(self, col, val):
        self.filters.append(("is", col, None if val == "null" else val))
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
            if op == "neq" and cur == val:
                return False
            if op == "in" and cur not in val:
                return False
            if op == "is" and cur != val:
                return False
            if op == "lt" and not (cur is not None and str(cur) < str(val)):
                return False
            if op == "gte" and not (cur is not None and str(cur) >= str(val)):
                return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        if self._mode == "select":
            matched = [dict(r) for r in rows if self._match(r)]
            if self._limit is not None:
                matched = matched[: self._limit]
            return FakeResponse(matched, count=len(matched))
        if self._mode == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched:
                r.update(self._payload)
            data = [dict(r) for r in matched] if self._returning else []
            return FakeResponse(data, count=len(matched))
        if self._mode == "delete":
            self.store[self.table] = [r for r in rows if not self._match(r)]
            return FakeResponse([])
        return FakeResponse([])


class FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return FakeQuery(self.store, name)


# ──────────────────────────────────────────────────────────────────────────────
# Fixture data
# ──────────────────────────────────────────────────────────────────────────────
NOW = datetime.now(timezone.utc)
FUTURE = (NOW + timedelta(days=4)).isoformat()
PAST = (NOW - timedelta(days=10)).isoformat()
PAST_DONE = (NOW - timedelta(days=30)).isoformat()

PENDING_DESC = "Finish the Q3 report"
MISSED_DESC = "Submit tax documents"      # stored pending+past -> mark_overdue flips to missed
DONE_DESC = "Renew passport"               # status=done -> excluded by our filter
DELETED_DESC = "Cancel gym membership"     # soft-deleted -> excluded by deleted_at guard

PROSE_SNIPPET = "overwhelmed"              # injected rag prose for the mixed case


def _deadline(did, *, status, due_date, description, deleted_at=None):
    return {
        "id": did,
        "user_id": USER,
        "description": description,
        "due_date": due_date,
        "status": status,
        "status_changed_at": NOW.isoformat(),
        "source_entry_id": "entry-1",
        "project_id": None,
        "deleted_at": deleted_at,
    }


def _install_fake():
    store = {
        "deadlines": [
            _deadline("d-pending", status="pending", due_date=FUTURE, description=PENDING_DESC),
            # stored as pending+past so mark_overdue_deadlines_as_missed reconciles
            # it to MISSED — the exact "overdue items slip naturally" path.
            _deadline("d-missed", status="pending", due_date=PAST, description=MISSED_DESC),
            _deadline("d-done", status="done", due_date=PAST_DONE, description=DONE_DESC),
            _deadline("d-del", status="pending", due_date=PAST, description=DELETED_DESC,
                      deleted_at=(NOW - timedelta(days=1)).isoformat()),
        ],
        "entries": [{"id": "entry-1", "user_id": USER, "status": "completed", "deleted_at": None}],
        "projects": [],
        "entities": [],
    }
    fake = FakeSupabase(store)
    deadline_service.supabase = fake
    project_service.supabase = fake
    context_assembler_mod.supabase = fake
    return store


def _initial_state(question: str, *, dashboard_context_needed: bool, rag_entries=None) -> dict:
    return {
        "question": question,
        "user_id": USER,
        "conversation_history": "",
        "long_term_memory": "",
        "user_timezone": "UTC",
        "query_types": [],
        "time_range": None,
        "entities_mentioned": [],          # empty -> context_assembler entity probe is a no-op (no network)
        "dashboard_context_needed": dashboard_context_needed,
        "today_str": NOW.date().isoformat(),
        "temporal_entries": [],
        "recent_summaries": [],
        "rag_entries": rag_entries or [],
        "dashboard_context": {},
        "rag_max_similarity": 0.7 if rag_entries else 0.0,
        "temporal_has_results": False,
        "dashboard_has_results": False,
        "is_low_confidence": False,
        "is_reask": False,
        "question_entity_known": None,
        "question_entity_check_details": {},
        "assembled_context": "",
        "answer": "",
    }


async def _assemble(question: str, *, dashboard_context_needed=True, rag_entries=None) -> str:
    """Run the real dashboard_context + context_assembler nodes, return the
    assembled context string the generation model would receive."""
    state = _initial_state(
        question,
        dashboard_context_needed=dashboard_context_needed,
        rag_entries=rag_entries,
    )
    state.update(await dashboard_context(state))
    state.update(await context_assembler(state))
    return state["assembled_context"], state


# ──────────────────────────────────────────────────────────────────────────────
# Cases
# ──────────────────────────────────────────────────────────────────────────────
async def _run_cases() -> list[dict]:
    cases: list[dict] = []

    # ── A: "what's due this week" -> pending appears, done excluded ──────────
    _install_fake()
    ctx, _ = await _assemble("what's due this week")
    cases.append({
        "id": "A_due_this_week",
        "question": "what's due this week",
        "checks": [
            (f"pending deadline {PENDING_DESC!r} present", PENDING_DESC in ctx),
            (f"completed deadline {DONE_DESC!r} excluded", DONE_DESC not in ctx),
        ],
        "context": ctx,
    })

    # ── B: "am I behind on anything" -> MISSED appears (THE bug case) ────────
    _install_fake()
    ctx, _ = await _assemble("am I behind on anything")
    cases.append({
        "id": "B_am_i_behind",
        "question": "am I behind on anything",
        "checks": [
            (f"MISSED deadline {MISSED_DESC!r} present (RED pre-fix)", MISSED_DESC in ctx),
            (f"soft-deleted deadline {DELETED_DESC!r} excluded", DELETED_DESC not in ctx),
            (f"completed deadline {DONE_DESC!r} excluded", DONE_DESC not in ctx),
        ],
        "context": ctx,
    })

    # ── C: mixed -> structured deadline AND prose both present (augment) ─────
    _install_fake()
    rag = [{
        "date": "3 days ago",
        "raw_text": "I've felt overwhelmed by everything piling up this month.",
        "relevance": "high",
    }]
    ctx, _ = await _assemble(
        "what's due soon and how have I been feeling about my deadlines",
        rag_entries=rag,
    )
    cases.append({
        "id": "C_mixed",
        "question": "what's due soon and how have I been feeling about my deadlines",
        "checks": [
            (f"structured deadline {PENDING_DESC!r} present", PENDING_DESC in ctx),
            (f"prose snippet {PROSE_SNIPPET!r} still present (not replaced)", PROSE_SNIPPET in ctx),
        ],
        "context": ctx,
    })

    return cases


def _run_trigger_check() -> dict:
    """Tolerant: is_deadline_query is added by fix #1. Pre-fix it doesn't exist,
    so this reports 'not implemented' (informational) rather than crashing."""
    try:
        from app.services.ask_service import is_deadline_query
    except ImportError:
        return {"id": "trigger", "implemented": False, "checks": []}

    deadline_qs = ["what's due this week", "am I behind on anything", "any overdue deadlines?"]
    off_topic = "what did I write about my dog"
    checks = [(f"is_deadline_query({q!r}) is True", bool(is_deadline_query(q))) for q in deadline_qs]
    checks.append((f"is_deadline_query({off_topic!r}) is False", not is_deadline_query(off_topic)))
    return {"id": "trigger", "implemented": True, "checks": checks}


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    cases = asyncio.run(_run_cases())
    trigger = _run_trigger_check()

    all_checks_blocks = cases + ([trigger] if trigger["checks"] else [])
    passed = sum(1 for b in all_checks_blocks for _, ok in b["checks"] if ok)
    failed = sum(1 for b in all_checks_blocks for _, ok in b["checks"] if not ok)
    status = "GREEN" if failed == 0 else "RED"

    print("=" * 72)
    print("ASK DEADLINE-CONTENT EVAL  (deterministic — asserts on assembled context)")
    print("=" * 72)
    for b in cases:
        print(f"\n[{b['id']}]  q={b['question']!r}")
        for desc, ok in b["checks"]:
            print(f"   {'PASS' if ok else 'FAIL'}  {desc}")
    if not trigger["implemented"]:
        print("\n[trigger]  is_deadline_query NOT YET IMPLEMENTED "
              "(expected pre-fix; fix #1 adds it)")
    else:
        print("\n[trigger]  is_deadline_query present")
        for desc, ok in trigger["checks"]:
            print(f"   {'PASS' if ok else 'FAIL'}  {desc}")

    print("\n" + "-" * 72)
    print(f"RESULT: {status}   ({passed} passed, {failed} failed)")
    print("-" * 72)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    out = RESULTS_DIR / f"ask_deadlines_eval_{ts}.json"
    out.write_text(json.dumps({
        "metadata": {"ran_at": ts, "git_commit": _git_sha(), "user_id": USER},
        "summary": {"status": status, "passed": passed, "failed": failed},
        "cases": [
            {"id": b["id"], "question": b["question"],
             "checks": [{"desc": d, "ok": ok} for d, ok in b["checks"]],
             "context": b["context"]}
            for b in cases
        ],
        "trigger": {
            "implemented": trigger["implemented"],
            "checks": [{"desc": d, "ok": ok} for d, ok in trigger["checks"]],
        },
    }, indent=2, default=str), encoding="utf-8")
    print(f"\n📁 Results: {out}")
    return 0 if status == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
