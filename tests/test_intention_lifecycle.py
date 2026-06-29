"""Hermetic tests for drift lifecycle — resolve / dismiss (drift P6).

intention_service.resolve_intention / dismiss_intention are the first
USER-triggered writes to the intentions table. They must be SOFT (status only,
never deleted_at), OWNERSHIP-scoped (a user can't touch another's row -> 404, no
mutation), IDEMPOTENT, and kept in LOCKSTEP with get_drift (a resolved/dismissed
row must vanish from the drift payload). Mocks the supabase PostgREST chain over
a shared in-memory store so the write and the subsequent read see the same rows.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import app.services.intention_service as svc


class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    """Honors select/update + eq/in_/is_ filters against a shared row list."""

    def __init__(self, store):
        self.store = store
        self.mode = "select"
        self.payload = None
        self.filters = []

    def select(self, *a, **k):
        self.mode = "select"
        return self

    def update(self, payload, returning=None):
        self.mode = "update"
        self.payload = payload
        return self

    def eq(self, c, v):
        self.filters.append(("eq", c, v))
        return self

    def in_(self, c, v):
        self.filters.append(("in", c, list(v)))
        return self

    def is_(self, c, v):
        self.filters.append(("is", c, None if v == "null" else v))
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def _match(self, r):
        for op, c, v in self.filters:
            cur = r.get(c)
            if op == "eq" and cur != v:
                return False
            if op == "in" and cur not in v:
                return False
            if op == "is" and cur != v:
                return False
        return True

    def execute(self):
        rows = [r for r in self.store if self._match(r)]
        if self.mode == "update":
            for r in rows:
                r.update(self.payload)
        return _Resp([dict(r) for r in rows])


class _FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return _Query(self.store)


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=6)).isoformat()


def _row(rid, status="active", days=40, user="u1"):
    return {
        "id": rid,
        "user_id": user,
        "text": rid,
        "status": status,
        "first_stated_at": _ago(days),
        "last_referenced_at": _ago(days),
        "reference_count": 1,
        "deleted_at": None,
    }


def _install(store):
    svc.supabase = _FakeSupabase(store)
    return store


def test_resolve_sets_status_and_excludes_from_drift(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    store = _install([_row("i1", days=46), _row("i2", days=80)])
    out = asyncio.run(svc.resolve_intention("u1", "i1"))
    assert out["status"] == "ok"
    assert out["intention"]["status"] == "resolved"
    assert store[0]["deleted_at"] is None  # soft — never deletes
    drift = asyncio.run(svc.get_drift("u1"))
    ids = [i["id"] for i in drift["intentions"]]
    assert "i1" not in ids   # lockstep: resolved row is gone from drift
    assert "i2" in ids


def test_dismiss_sets_status_and_excludes_from_drift(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    store = _install([_row("i1", days=46), _row("i2", days=80)])
    out = asyncio.run(svc.dismiss_intention("u1", "i1"))
    assert out["intention"]["status"] == "dismissed"
    drift = asyncio.run(svc.get_drift("u1"))
    assert "i1" not in [i["id"] for i in drift["intentions"]]


def test_ownership_rejected_404_no_mutation(monkeypatch):
    store = _install([_row("i1", status="active")])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(svc.resolve_intention("someone-else", "i1"))
    assert exc.value.status_code == 404
    assert store[0]["status"] == "active"   # untouched


def test_missing_id_404(monkeypatch):
    _install([_row("i1")])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(svc.dismiss_intention("u1", "does-not-exist"))
    assert exc.value.status_code == 404


def test_resolve_is_idempotent(monkeypatch):
    store = _install([_row("i1", status="active")])
    first = asyncio.run(svc.resolve_intention("u1", "i1"))
    second = asyncio.run(svc.resolve_intention("u1", "i1"))   # already resolved
    assert first["intention"]["status"] == "resolved"
    assert second["status"] == "ok"
    assert second["intention"]["status"] == "resolved"


def test_soft_deleted_row_not_resolvable_404(monkeypatch):
    store = _install([_row("i1")])
    store[0]["deleted_at"] = _ago(1)   # already soft-deleted
    with pytest.raises(HTTPException) as exc:
        asyncio.run(svc.resolve_intention("u1", "i1"))
    assert exc.value.status_code == 404


def test_get_drift_excludes_terminal_statuses(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    _install([
        _row("active1", status="active", days=50),
        _row("resolved1", status="resolved", days=50),
        _row("dismissed1", status="dismissed", days=50),
    ])
    ids = [i["id"] for i in asyncio.run(svc.get_drift("u1"))["intentions"]]
    assert ids == ["active1"]
