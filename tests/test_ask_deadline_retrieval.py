"""Regression tests for the Ask deadline-retrieval fix.

The deadline path already existed (dashboard_context -> list_deadlines ->
context_assembler injects a deadlines block) but was broken three ways:
  1. fired only on an unreliable LLM boolean (dashboard_context_needed)
  2. PENDING-ONLY (status=None), so missed/overdue deadlines were filtered out
     before the model saw them -> "am I behind" was unanswerable
  3. terse, status-less formatting

Plus the trap: dashboard_has_results feeds _compute_low_confidence as a
corroborating signal, so fetching deadlines for EVERY query would mark off-topic
queries high-confidence and break the honest-refusal path. The fetch therefore
stays GATED behind the deadline trigger.

These run against a tiny in-memory fake of the supabase PostgREST chain (same
shape as tests/test_deadline_soft_delete.py); assertions are behavioural (what
ends up in the assembled context the generation model receives), not "did we call
.is_()". Sync tests via asyncio.run — no pytest-asyncio needed.
"""

import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "dummy-key-no-network")
os.environ.pop("USE_VERTEX", None)

import asyncio
from datetime import datetime, timedelta, timezone

import app.services.ask_pipeline.context_assembler as context_assembler_mod
import app.services.deadline_service as deadline_service
import app.services.project_service as project_service
from app.services.ask_pipeline.context_assembler import (
    _compute_low_confidence,
    context_assembler,
)
from app.services.ask_pipeline.dashboard_context import dashboard_context
from app.services.ask_service import is_deadline_query

USER = "user-1"
NOW = datetime.now(timezone.utc)
FUTURE = (NOW + timedelta(days=4)).isoformat()
PAST = (NOW - timedelta(days=10)).isoformat()
PAST_DONE = (NOW - timedelta(days=30)).isoformat()


# --------------------------------------------------------------------------- #
# Fake supabase PostgREST chain
# --------------------------------------------------------------------------- #
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


def install(monkeypatch, deadlines):
    store = {
        "deadlines": [dict(d) for d in deadlines],
        "entries": [{"id": "entry-1", "user_id": USER, "status": "completed", "deleted_at": None}],
        "projects": [],
        "entities": [],
    }
    fake = FakeSupabase(store)
    for mod in (deadline_service, project_service, context_assembler_mod):
        monkeypatch.setattr(mod, "supabase", fake)
    return store


def _state(question, *, dashboard_context_needed=False, rag_entries=None):
    return {
        "question": question,
        "user_id": USER,
        "conversation_history": "",
        "long_term_memory": "",
        "user_timezone": "UTC",
        "query_types": [],
        "time_range": None,
        "entities_mentioned": [],
        "dashboard_context_needed": dashboard_context_needed,
        "today_str": NOW.date().isoformat(),
        "temporal_entries": [],
        "recent_summaries": [],
        "rag_entries": rag_entries or [],
        "dashboard_context": {},
        "rag_max_similarity": 0.0,
        "temporal_has_results": False,
        "dashboard_has_results": False,
        "is_low_confidence": False,
        "is_reask": False,
        "question_entity_known": None,
        "question_entity_check_details": {},
        "assembled_context": "",
        "answer": "",
    }


# --------------------------------------------------------------------------- #
# Fix #1 — is_deadline_query trigger
# --------------------------------------------------------------------------- #
def test_is_deadline_query_matches_high_signal_phrasings():
    for q in [
        "what's due this week",
        "what deadlines do I have",
        "am I behind on anything",
        "anything overdue?",
        "is the report due soon",
        "by when do I need to finish this",
        "am I falling behind",
    ]:
        assert is_deadline_query(q), q


def test_is_deadline_query_rejects_non_deadline_questions():
    for q in [
        "what did I write about my dog",
        "how am I feeling lately",
        "what should I produce next",   # 'due' inside 'produce' must NOT match
        "tell me the story behind my tattoo",  # bare 'behind' must NOT match
        "summarize my week",
    ]:
        assert not is_deadline_query(q), q


# --------------------------------------------------------------------------- #
# Fix #2 — broadened status: missed/overdue now surfaced
# --------------------------------------------------------------------------- #
def test_dashboard_context_includes_missed_deadlines(monkeypatch):
    install(monkeypatch, [
        _deadline("d-pending", status="pending", due_date=FUTURE, description="Finish report"),
        # pending+past -> mark_overdue_deadlines_as_missed flips it to missed
        _deadline("d-missed", status="pending", due_date=PAST, description="Submit taxes"),
        _deadline("d-done", status="done", due_date=PAST_DONE, description="Renew passport"),
    ])
    out = asyncio.run(dashboard_context(_state("am I behind on anything",
                                               dashboard_context_needed=True)))
    deadlines = out["dashboard_context"]["deadlines"]
    blob = " || ".join(deadlines)
    assert "Submit taxes" in blob       # the overdue one — the bug fix
    assert "Finish report" in blob      # pending still present
    assert "Renew passport" not in blob  # done excluded
    assert out["dashboard_has_results"] is True


# --------------------------------------------------------------------------- #
# Fix #1 backstop — heuristic fires the fetch even with the LLM flag off
# --------------------------------------------------------------------------- #
def test_dashboard_context_fires_on_heuristic_without_llm_flag(monkeypatch):
    install(monkeypatch, [
        _deadline("d-missed", status="pending", due_date=PAST, description="Submit taxes"),
    ])
    out = asyncio.run(dashboard_context(_state("am I behind on anything",
                                               dashboard_context_needed=False)))
    assert out.get("dashboard_has_results") is True
    assert "Submit taxes" in " || ".join(out["dashboard_context"]["deadlines"])


# --------------------------------------------------------------------------- #
# Fix #3 — richer status-tagged formatting in the assembled context
# --------------------------------------------------------------------------- #
def test_assembler_renders_status_tagged_deadline_block(monkeypatch):
    install(monkeypatch, [
        _deadline("d-pending", status="pending", due_date=FUTURE, description="Finish report"),
        _deadline("d-missed", status="pending", due_date=PAST, description="Submit taxes"),
    ])
    state = _state("am I behind on anything", dashboard_context_needed=True)
    state.update(asyncio.run(dashboard_context(state)))
    state.update(asyncio.run(context_assembler(state)))
    ctx = state["assembled_context"]
    assert "Deadlines:" in ctx
    assert "Submit taxes — was due" in ctx and "(overdue)" in ctx
    assert "Finish report — due" in ctx and "(pending)" in ctx
    # Old label retired now that overdue rows are included.
    assert "Upcoming deadlines:" not in ctx


def test_assembler_keeps_prose_alongside_deadlines_for_mixed_query(monkeypatch):
    install(monkeypatch, [
        _deadline("d-pending", status="pending", due_date=FUTURE, description="Finish report"),
    ])
    rag = [{"date": "3 days ago", "raw_text": "I felt overwhelmed by it all.", "relevance": "high"}]
    state = _state("what's due and how do I feel about it",
                   dashboard_context_needed=True, rag_entries=rag)
    state["rag_max_similarity"] = 0.7
    state.update(asyncio.run(dashboard_context(state)))
    state.update(asyncio.run(context_assembler(state)))
    ctx = state["assembled_context"]
    assert "Finish report" in ctx          # structured deadline
    assert "overwhelmed" in ctx            # prose NOT replaced (augment)


# --------------------------------------------------------------------------- #
# Step 3 GUARDRAIL — off-topic query from a user WITH deadlines must not
# fetch deadlines, must not mark dashboard_has_results, must stay low-confidence
# --------------------------------------------------------------------------- #
def test_offtopic_query_with_deadlines_does_not_fetch_or_falsely_corroborate(monkeypatch):
    install(monkeypatch, [
        _deadline("d-pending", status="pending", due_date=FUTURE, description="Finish report"),
        _deadline("d-missed", status="pending", due_date=PAST, description="Submit taxes"),
    ])
    # Off-topic, LLM flag off, no deadline phrasing -> the fetch must NOT fire.
    out = asyncio.run(dashboard_context(_state("what did I write about my dog",
                                               dashboard_context_needed=False)))
    assert out == {}, "dashboard_context fetched for an off-topic query (guardrail breach)"


def test_offtopic_query_stays_low_confidence_despite_user_having_deadlines(monkeypatch):
    install(monkeypatch, [
        _deadline("d-pending", status="pending", due_date=FUTURE, description="Finish report"),
    ])
    # Simulate the full off-topic path: dashboard didn't fire, no rag/temporal hits.
    state = _state("what did I write about my dog", dashboard_context_needed=False)
    state.update(asyncio.run(dashboard_context(state)))  # -> {} ; dashboard_has_results stays False
    assert not state.get("dashboard_has_results")
    # The refusal gate must still trip — deadlines on the books must not rescue it.
    assert _compute_low_confidence(state) is True
