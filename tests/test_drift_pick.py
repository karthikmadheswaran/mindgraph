"""Hermetic tests for drift pick v1 (single-pick mode of /intentions/drift).

RED-first, per house rules: written against the intended contract BEFORE the
implementation. Covers eligibility filters (threshold / 90d cap / 14d cooldown),
48h pick stickiness (same-day stability), rotation after the sticky window,
scoring (reference-count weighting + never-surfaced bonus), the surfaced_at
stamp, the self-judgment guard (with the real prod fixtures), and the three
backend PostHog events (drift_card_served / intention_resolved /
intention_dismissed). Mocks the supabase PostgREST chain (no DB) and the
analytics client (no PostHog).
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
    """Honors the select/update chains. Selects return the seeded rows; updates
    are recorded on the fake (payload + the id it was scoped to) and return the
    matching row so lifecycle code can read it back."""

    def __init__(self, fake):
        self._fake = fake
        self._mode = "select"
        self._payload = None
        self._eq_id = None

    def select(self, *a, **k):
        self._mode = "select"
        return self

    def update(self, payload, *a, **k):
        self._mode = "update"
        self._payload = payload
        return self

    def eq(self, field, value):
        if field == "id":
            self._eq_id = value
        return self

    def in_(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def execute(self):
        if self._mode == "update":
            self._fake.updates.append({"id": self._eq_id, "payload": self._payload})
            matched = [r for r in self._fake.rows if r.get("id") == self._eq_id]
            merged = [{**r, **self._payload} for r in matched]
            return _Resp(merged)
        return _Resp(self._fake.rows)


class _FakeSupabase:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def table(self, name):
        return _Chain(self)


def _ago(days=0, hours=0):
    # 6h cushion on day-granular stamps so integer .days can't tip a boundary.
    return (
        datetime.now(timezone.utc) - timedelta(days=days, hours=hours)
    ).isoformat()


def _row(text, days_ago, status="active", refs=1, surfaced=None, **over):
    r = {
        "id": f"id-{text}",
        "text": text,
        "first_stated_at": _ago(days=days_ago, hours=6),
        "last_referenced_at": _ago(days=days_ago, hours=6),
        "reference_count": refs,
        "status": status,
        "surfaced_at": surfaced,
    }
    r.update(over)
    return r


def _pick(rows, monkeypatch=None, **kw):
    fake = _FakeSupabase(rows)
    svc.supabase = fake
    return fake, asyncio.run(svc.pick_drift("user-1", **kw))


class _TrackRecorder:
    def __init__(self):
        self.events = []

    def __call__(self, user_id, event, properties=None):
        self.events.append((user_id, event, properties or {}))


# ── Self-judgment guard (hard requirement; real prod fixtures) ────────────────


def test_guard_unit_real_fixtures():
    # The two real prod phrasings MUST be excluded — this is the hard gate.
    assert svc.is_self_judgment("Not be a useless guy") is True
    assert svc.is_self_judgment("Have an identity") is True
    # Ordinary do-able intentions pass through.
    assert svc.is_self_judgment("get gym membership") is False
    assert svc.is_self_judgment("call the bank about the refund") is False
    assert svc.is_self_judgment("ship the drift feature") is False
    # Conservative default: unverifiable text is excluded, never served.
    assert svc.is_self_judgment("") is True
    assert svc.is_self_judgment(None) is True


def test_pick_never_serves_self_judgment(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    rows = [
        _row("Not be a useless guy", 40, refs=9),   # highest score if unguarded
        _row("Have an identity", 35, refs=5),
        _row("start working out", 30),
    ]
    _, out = _pick(rows)
    assert out["pick"] is not None
    assert out["pick"]["id"] == "id-start working out"


def test_pick_returns_none_when_only_self_judgment(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    rows = [_row("Not be a useless guy", 40), _row("Have an identity", 35)]
    fake, out = _pick(rows)
    assert out["pick"] is None
    assert fake.updates == []   # nothing stamped, nothing served


# ── Eligibility filters ───────────────────────────────────────────────────────


def test_below_threshold_not_eligible(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    _, out = _pick([_row("fresh", 5)])   # 5 < default 14
    assert out["pick"] is None


def test_over_90_days_not_eligible(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    _, out = _pick([_row("ancient", 120)])
    assert out["pick"] is None


def test_cooldown_14d_excludes_recently_surfaced(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    # Surfaced 3 days ago: outside the 48h sticky window, inside the 14d
    # cooldown -> not re-picked; with no other candidates the pick is None.
    _, out = _pick([_row("gym", 30, surfaced=_ago(days=3))])
    assert out["pick"] is None


def test_cooldown_expired_is_eligible_again(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    _, out = _pick([_row("gym", 30, surfaced=_ago(days=20))])
    assert out["pick"] is not None
    assert out["pick"]["id"] == "id-gym"


# ── Stickiness (same-day stability) + rotation ────────────────────────────────


def test_sticky_pick_within_48h_no_restamp_no_event(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    recorder = _TrackRecorder()
    monkeypatch.setattr(svc, "track", recorder)
    rows = [
        _row("gym", 30, surfaced=_ago(hours=2)),   # served 2h ago -> sticky
        _row("bank", 40),                           # would win a fresh pick
    ]
    fake, out = _pick(rows)
    assert out["pick"]["id"] == "id-gym"           # SAME pick, not a new one
    assert fake.updates == []                       # no restamp
    assert recorder.events == []                    # no duplicate served event


def test_rotates_after_48h_unacted(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    rows = [
        _row("gym", 30, surfaced=_ago(hours=60)),   # sticky window over; 14d cooldown blocks re-pick
        _row("bank", 40),
    ]
    _, out = _pick(rows)
    assert out["pick"]["id"] == "id-bank"


def test_acted_pick_rotates_immediately(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    # The sticky pick was resolved (status outside the live whitelist ->
    # not returned by the select at all); the pick must move on without
    # waiting out the 48h window.
    rows = [_row("bank", 40)]
    _, out = _pick(rows)
    assert out["pick"]["id"] == "id-bank"


# ── Scoring ───────────────────────────────────────────────────────────────────


def test_reference_count_outweighs_band(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    rows = [
        _row("once", 20, refs=1),    # band 1.0, refs term 2.0*log2(2)=2.0 -> 3.5 w/ bonus
        _row("often", 20, refs=5),   # refs term 2.0*log2(6)≈5.17 -> 6.67 w/ bonus
    ]
    _, out = _pick(rows)
    assert out["pick"]["id"] == "id-often"


def test_maturity_band_peaks_7_to_35(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    # Same refs; 20d sits in the peak band, 85d has tapered nearly to zero.
    rows = [_row("peak", 20), _row("tapered", 85)]
    _, out = _pick(rows)
    assert out["pick"]["id"] == "id-peak"


def test_never_surfaced_bonus_breaks_tie(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    rows = [
        _row("seen before", 20, surfaced=_ago(days=20)),   # cooldown expired, no bonus
        _row("never seen", 20),                             # +0.5 bonus
    ]
    _, out = _pick(rows)
    assert out["pick"]["id"] == "id-never seen"


# ── Serve side effects: stamp + drift_card_served ─────────────────────────────


def test_fresh_pick_stamps_surfaced_at(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    monkeypatch.setattr(svc, "track", _TrackRecorder())
    fake, out = _pick([_row("gym", 30)])
    assert out["pick"]["id"] == "id-gym"
    assert len(fake.updates) == 1
    assert fake.updates[0]["id"] == "id-gym"
    assert "surfaced_at" in fake.updates[0]["payload"]


def test_fresh_pick_fires_drift_card_served(monkeypatch):
    monkeypatch.delenv("DRIFT_THRESHOLD_DAYS", raising=False)
    recorder = _TrackRecorder()
    monkeypatch.setattr(svc, "track", recorder)
    _, out = _pick([_row("gym", 30, refs=3)])
    assert len(recorder.events) == 1
    user_id, event, props = recorder.events[0]
    assert user_id == "user-1"
    assert event == "drift_card_served"
    assert props["intention_id"] == "id-gym"
    assert props["days_since"] == 30
    assert props["reference_count"] == 3
    assert props["score"] == out["pick"]["score"]
    assert props["score"] > 0


# ── Lifecycle events: intention_resolved / intention_dismissed ────────────────


def _run_lifecycle(fn, rows, recorder):
    fake = _FakeSupabase(rows)
    svc.supabase = fake
    return asyncio.run(fn("user-1", rows[0]["id"]))


def test_resolve_fires_intention_resolved(monkeypatch):
    recorder = _TrackRecorder()
    monkeypatch.setattr(svc, "track", recorder)
    _run_lifecycle(svc.resolve_intention, [_row("gym", 30)], recorder)
    assert len(recorder.events) == 1
    user_id, event, props = recorder.events[0]
    assert user_id == "user-1"
    assert event == "intention_resolved"
    assert props["intention_id"] == "id-gym"
    assert props["days_since"] == 30


def test_dismiss_fires_intention_dismissed(monkeypatch):
    recorder = _TrackRecorder()
    monkeypatch.setattr(svc, "track", recorder)
    _run_lifecycle(svc.dismiss_intention, [_row("gym", 30)], recorder)
    assert len(recorder.events) == 1
    _, event, props = recorder.events[0]
    assert event == "intention_dismissed"
    assert props["intention_id"] == "id-gym"
    assert props["days_since"] == 30
