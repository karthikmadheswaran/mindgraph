"""Hermetic tests for the read-time drift endpoint (drift P4).

intention_service.get_drift reads live intentions and computes, per request,
drift_days = days_since(last_referenced_at), tagging is_drifting against an
env-tunable threshold. Mocks the supabase PostgREST chain (no DB). Timestamps
are relative to now() so drift_days is deterministic; a 6h cushion keeps the
.days count off the boundary regardless of get_drift's slightly-later now().
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

import asyncio
from datetime import datetime, timedelta, timezone

import app.services.intention_service as svc


class _Resp:
    def __init__(self, data):
        self.data = data


class _Chain:
    """Honors the select/eq/in_/is_ chain and returns the seeded rows."""

    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        return _Resp(self._rows)


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        return _Chain(self._rows)


def _ago(days):
    # 6h cushion so the integer .days count can't tip across a boundary when
    # get_drift computes its own (microseconds-later) now().
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=6)).isoformat()


def _row(text, days_ago, status="active", refs=1, **over):
    r = {
        "id": f"id-{text}",
        "text": text,
        "first_stated_at": _ago(days_ago),
        "last_referenced_at": _ago(days_ago),
        "reference_count": refs,
        "status": status,
    }
    r.update(over)
    return r


def _run(rows, **kw):
    svc.supabase = _FakeSupabase(rows)
    return asyncio.run(svc.get_drift("user-1", **kw))


def test_drift_days_computed(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    out = _run([_row("gym", 46)])
    item = out["intentions"][0]
    assert item["drift_days"] == 46
    assert item["text"] == "gym"
    assert item["id"] == "id-gym"


def test_is_drifting_threshold_default_14(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    out = _run([_row("fresh", 5), _row("stale", 20)])
    by_text = {i["text"]: i for i in out["intentions"]}
    assert out["threshold_days"] == 14
    assert by_text["fresh"]["is_drifting"] is False   # 5 < 14
    assert by_text["stale"]["is_drifting"] is True    # 20 >= 14


def test_threshold_override_param(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    out = _run([_row("a", 20), _row("b", 46)], threshold_days=30)
    by_text = {i["text"]: i for i in out["intentions"]}
    assert out["threshold_days"] == 30
    assert by_text["a"]["is_drifting"] is False   # 20 < 30
    assert by_text["b"]["is_drifting"] is True    # 46 >= 30


def test_env_threshold_read_per_request(monkeypatch):
    monkeypatch.setenv("DRIFT_THRESHOLD_DAYS", "60")
    out = _run([_row("x", 46)])
    assert out["threshold_days"] == 60
    assert out["intentions"][0]["is_drifting"] is False   # 46 < 60


def test_sorted_drift_descending(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    out = _run([_row("mid", 30), _row("old", 87), _row("new", 3)])
    days = [i["drift_days"] for i in out["intentions"]]
    assert days == sorted(days, reverse=True)
    assert days[0] == 87
    assert days[-1] == 3


def test_returns_all_rows_not_just_drifting(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    out = _run([_row("fresh", 1), _row("old", 99)])
    assert len(out["intentions"]) == 2   # both returned, not only the drifting one


def test_failsafe_bad_timestamp_does_not_crash(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    rows = [
        _row("good", 46),
        _row("nullts", 10, last_referenced_at=None),
        _row("garbage", 10, last_referenced_at="not-a-date"),
    ]
    out = _run(rows)   # must not raise
    by_text = {i["text"]: i for i in out["intentions"]}
    assert by_text["good"]["drift_days"] == 46
    assert by_text["nullts"]["drift_days"] is None
    assert by_text["nullts"]["is_drifting"] is False
    assert by_text["garbage"]["drift_days"] is None
    assert by_text["garbage"]["is_drifting"] is False
    # uncomputable rows sink to the bottom; the real one is on top
    assert out["intentions"][0]["drift_days"] == 46
    assert out["intentions"][-1]["drift_days"] is None
