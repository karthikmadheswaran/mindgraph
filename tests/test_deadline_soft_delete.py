"""Per-surface soft-delete tests for deadlines (migration 017 + service changes).

The point of soft-delete is that a deleted deadline disappears from EVERY read
surface, not just the dashboard feed. Each leak point from the C2 audit gets its
own assertion here:

  #1 feed      -> deadline_service.list_deadlines
  #2 count     -> compute_discoveries._unmet_deadline_echo ("N past deadlines still open")
  #3 progress  -> project_service.get_progress
  #4 insights  -> insights_engine.fetch_deadlines
  #5/#6 guards -> update_deadline_status / update_deadline_date 404 on a deleted row
  restore      -> delete -> gone -> restore -> back; restore into a live duplicate -> 409

These run against a tiny in-memory fake of the supabase PostgREST chain that
honours .is_("deleted_at","null") + the partial-unique constraint, so the
assertions are behavioural (rows in/out), not "did we call .is_()".
"""

import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

import asyncio

import pytest
from fastapi import HTTPException

import app.services.deadline_service as deadline_service
import app.services.project_service as project_service
import app.services.entry_service as entry_service
import app.insights_engine as insights_engine
import app.nodes.compute_discoveries as compute_discoveries

USER = "user-1"
PAST = "2020-01-01T00:00:00+00:00"
FUTURE = "2030-01-01T00:00:00+00:00"


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

    def select(self, *args, **kwargs):
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

    def order(self, *args, **kwargs):
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
            reviving = (
                self.table == "deadlines"
                and "deleted_at" in self._payload
                and self._payload["deleted_at"] is None
            )
            if reviving:
                for r in matched:
                    key = (
                        r.get("source_entry_id"),
                        (r.get("description") or "").lower(),
                        r.get("due_date"),
                    )
                    for other in rows:
                        if other is r or other.get("deleted_at") is not None:
                            continue
                        other_key = (
                            other.get("source_entry_id"),
                            (other.get("description") or "").lower(),
                            other.get("due_date"),
                        )
                        if other_key == key:
                            raise Exception(
                                "23505 duplicate key value violates unique constraint "
                                '"idx_deadlines_source_entry_description_due_date"'
                            )
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


def make_deadline(did, *, status="pending", due_date=FUTURE, deleted_at=None,
                  description="Finish report", source_entry_id="entry-1"):
    return {
        "id": did,
        "user_id": USER,
        "description": description,
        "due_date": due_date,
        "status": status,
        "status_changed_at": "2026-01-01T00:00:00+00:00",
        "source_entry_id": source_entry_id,
        "project_id": None,
        "deleted_at": deleted_at,
    }


def install(monkeypatch, deadlines, entries=None):
    """Wire one shared fake into every module that reads the deadlines table."""
    store = {
        "deadlines": [dict(d) for d in deadlines],
        "entries": entries
        if entries is not None
        else [{"id": "entry-1", "user_id": USER, "status": "completed", "deleted_at": None}],
        "projects": [],
        "entities": [],
    }
    fake = FakeSupabase(store)
    for mod in (deadline_service, project_service, entry_service,
                insights_engine, compute_discoveries):
        monkeypatch.setattr(mod, "supabase", fake)
    return store


# ---- #1 feed -------------------------------------------------------------

def test_feed_excludes_soft_deleted(monkeypatch):
    install(monkeypatch, [
        make_deadline("d-live"),
        make_deadline("d-del", deleted_at="2026-06-18T00:00:00+00:00"),
    ])
    result = asyncio.run(deadline_service.list_deadlines(None, USER))
    ids = [d["id"] for d in result["deadlines"]]
    assert ids == ["d-live"]


# ---- #2 "N past deadlines still open" count ------------------------------

def test_past_open_count_excludes_soft_deleted(monkeypatch):
    install(monkeypatch, [
        make_deadline("d-live", due_date=PAST),
        make_deadline("d-del", due_date=PAST, deleted_at="2026-06-18T00:00:00+00:00"),
    ])
    echo = compute_discoveries._unmet_deadline_echo(USER, has_deadline=True)
    assert echo is not None and echo["count"] == 1
    assert echo["phrase"] == "1 past deadline still open"


def test_past_open_count_zero_when_all_deleted(monkeypatch):
    install(monkeypatch, [
        make_deadline("d-del", due_date=PAST, deleted_at="2026-06-18T00:00:00+00:00"),
    ])
    assert compute_discoveries._unmet_deadline_echo(USER, has_deadline=True) is None


# ---- #3 progress ---------------------------------------------------------

def test_progress_excludes_soft_deleted(monkeypatch):
    install(monkeypatch, [
        make_deadline("d-done-live", status="done"),
        make_deadline("d-done-del", status="done", deleted_at="2026-06-18T00:00:00+00:00"),
    ])
    progress = asyncio.run(project_service.get_progress(USER))
    ids = [d["id"] for d in progress["deadlines"]]
    assert ids == ["d-done-live"]


# ---- #4 insights ---------------------------------------------------------

def test_insights_fetch_excludes_soft_deleted(monkeypatch):
    install(monkeypatch, [
        make_deadline("d-live"),
        make_deadline("d-del", deleted_at="2026-06-18T00:00:00+00:00"),
    ])
    rows = insights_engine.fetch_deadlines(USER)
    assert [d["id"] for d in rows] == ["d-live"]


# ---- #5/#6 PATCH guards (resurrection guard) -----------------------------

def test_status_change_on_deleted_is_404(monkeypatch):
    install(monkeypatch, [make_deadline("d-del", deleted_at="2026-06-18T00:00:00+00:00")])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(deadline_service.update_deadline_status("d-del", "done", USER))
    assert exc.value.status_code == 404


def test_date_edit_on_deleted_is_404(monkeypatch):
    install(monkeypatch, [make_deadline("d-del", deleted_at="2026-06-18T00:00:00+00:00")])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(deadline_service.update_deadline_date("d-del", "2031-01-01", USER))
    assert exc.value.status_code == 404


# ---- soft delete + restore round-trip ------------------------------------

def test_delete_is_soft_then_restore_round_trip(monkeypatch):
    store = install(monkeypatch, [make_deadline("d-1")])

    asyncio.run(deadline_service.delete_deadline("d-1", USER))
    # Row still exists (soft), but is now stamped + absent from the feed.
    assert store["deadlines"][0]["deleted_at"] is not None
    assert asyncio.run(deadline_service.list_deadlines(None, USER))["deadlines"] == []

    restored = asyncio.run(deadline_service.restore_deadline("d-1", USER))
    assert restored["deleted_at"] is None
    ids = [d["id"] for d in asyncio.run(deadline_service.list_deadlines(None, USER))["deadlines"]]
    assert ids == ["d-1"]


def test_restore_into_live_duplicate_is_409(monkeypatch):
    install(monkeypatch, [
        make_deadline("d-del", deleted_at="2026-06-18T00:00:00+00:00",
                      description="Finish report", due_date=FUTURE),
        make_deadline("d-live", description="Finish report", due_date=FUTURE),  # live dup
    ])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(deadline_service.restore_deadline("d-del", USER))
    assert exc.value.status_code == 409
