"""Hermetic tests for Patterns v1 (founder-gated, graph-v2-patterns.md).

Two read-only aggregation routes — GET /patterns/attention-mix (weekly
entry_tags buckets) and GET /patterns/gravity (entity share of entries,
30d window vs prior window) — both behind patterns_enabled: PATTERNS_ENABLED
env flag (default OFF) OR the founder account id. Trial users get 404 (not
403) so the surface stays invisible.

Also locks the drift pick-mode route contract: Patterns v1 reuses the
non-pick drift read path and must leave ?pick=true untouched.

All DB mocked; routes driven via TestClient, aggregation via the service.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
import app.services.patterns_service as svc

FOUNDER = svc.FOUNDER_USER_ID
TRIAL = "trial-uid-not-founder"


# ── Fake supabase: per-table rows + a call log so filter chains are checkable ──


class _Resp:
    def __init__(self, data):
        self.data = data


class _Chain:
    def __init__(self, rows, log):
        self._rows = rows
        self._log = log

    def _record(self, name, args):
        self._log.append((name, args))
        return self

    def select(self, *a, **k):
        return self._record("select", a)

    def eq(self, *a, **k):
        return self._record("eq", a)

    def in_(self, *a, **k):
        return self._record("in_", a)

    def is_(self, *a, **k):
        return self._record("is_", a)

    def gte(self, *a, **k):
        return self._record("gte", a)

    def lt(self, *a, **k):
        return self._record("lt", a)

    def order(self, *a, **k):
        return self._record("order", a)

    def limit(self, *a, **k):
        return self._record("limit", a)

    def execute(self):
        return _Resp(self._rows)


class _FakeSupabase:
    """table(name) -> chain over the seeded rows; every filter call is logged
    per table so tests can assert e.g. the deleted_at IS NULL guard."""

    def __init__(self, tables):
        self._tables = tables
        self.calls = {name: [] for name in tables}

    def table(self, name):
        self.calls.setdefault(name, [])
        return _Chain(self._tables.get(name, []), self.calls[name])


# ── Route-level: auth + gate ───────────────────────────────────────────────────


@pytest.fixture
def anon_client():
    return TestClient(app)


def _client_as(uid):
    app.dependency_overrides[get_current_user] = lambda: uid
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_overrides_and_env(monkeypatch):
    monkeypatch.delenv("PATTERNS_ENABLED", raising=False)
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("route", ["/patterns/attention-mix", "/patterns/gravity"])
def test_patterns_routes_require_auth(anon_client, route):
    resp = anon_client.get(route)
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize("route", ["/patterns/attention-mix", "/patterns/gravity"])
def test_gate_hides_routes_from_non_founder(route):
    client = _client_as(TRIAL)
    with patch("app.main.track"):
        resp = client.get(route)
    assert resp.status_code == 404


def test_gate_founder_passes():
    client = _client_as(FOUNDER)
    with patch("app.main.track"), patch.object(
        svc, "get_attention_mix", AsyncMock(return_value={"weeks": []})
    ):
        resp = client.get("/patterns/attention-mix")
    assert resp.status_code == 200


def test_gate_env_flag_enables_for_everyone(monkeypatch):
    monkeypatch.setenv("PATTERNS_ENABLED", "1")
    client = _client_as(TRIAL)
    with patch("app.main.track"), patch.object(
        svc, "get_gravity", AsyncMock(return_value={"entities": []})
    ):
        resp = client.get("/patterns/gravity")
    assert resp.status_code == 200


def test_patterns_viewed_event_fires_on_attention_mix():
    client = _client_as(FOUNDER)
    with patch("app.main.track") as track, patch.object(
        svc, "get_attention_mix", AsyncMock(return_value={"weeks": []})
    ):
        client.get("/patterns/attention-mix")
    events = [c.args[1] for c in track.call_args_list]
    assert "patterns_viewed" in events


def test_graph_viewed_event_fires_on_entity_relations():
    client = _client_as(FOUNDER)
    with patch("app.main.track") as track, patch(
        "app.services.entity_service.get_entity_relations",
        AsyncMock(return_value={"relations": []}),
    ):
        resp = client.get("/entity-relations")
    assert resp.status_code == 200
    events = [c.args[1] for c in track.call_args_list]
    assert "graph_viewed" in events


# ── Drift regression: Patterns v1 must not touch pick-mode ────────────────────


def test_drift_pick_mode_route_passthrough_unchanged():
    client = _client_as(FOUNDER)
    payload = {"threshold_days": 14, "pick": {"id": "i1", "text": "gym"}}
    with patch(
        "app.services.intention_service.pick_drift",
        AsyncMock(return_value=payload),
    ) as pick:
        resp = client.get("/intentions/drift?pick=true")
    assert resp.status_code == 200
    assert resp.json() == payload
    pick.assert_awaited_once_with(FOUNDER, None)


def test_drift_non_pick_route_passthrough_unchanged():
    client = _client_as(FOUNDER)
    payload = {"threshold_days": 14, "intentions": []}
    with patch(
        "app.services.intention_service.get_drift",
        AsyncMock(return_value=payload),
    ) as get:
        resp = client.get("/intentions/drift")
    assert resp.status_code == 200
    assert resp.json() == payload
    get.assert_awaited_once_with(FOUNDER, None)


# ── Service-level: attention mix aggregation ──────────────────────────────────


def _week_start_utc(now=None):
    now = now or datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).date()
    return monday


def test_attention_mix_buckets_weekly_and_lists_all_categories():
    this_monday = _week_start_utc()
    in_this_week = datetime(
        this_monday.year, this_monday.month, this_monday.day, 12, tzinfo=timezone.utc
    )
    prev_week = in_this_week - timedelta(days=7)

    fake = _FakeSupabase(
        {
            "entries": [
                {"id": 1, "created_at": in_this_week.isoformat()},
                {"id": 2, "created_at": prev_week.isoformat()},
            ],
            "entry_tags": [
                {"entry_id": 1, "category": "work"},
                {"entry_id": 1, "category": "health"},
                {"entry_id": 2, "category": "work"},
            ],
        }
    )
    with patch.object(svc, "supabase", fake):
        out = asyncio.run(svc.get_attention_mix("user-1"))

    assert len(out["categories"]) == 9
    assert out["weeks"], "expected weekly buckets"
    starts = [w["week_start"] for w in out["weeks"]]
    assert starts == sorted(starts)
    assert len(out["weeks"]) == svc.ATTENTION_WEEKS
    by_start = {w["week_start"]: w["counts"] for w in out["weeks"]}
    assert by_start[this_monday.isoformat()] == {"work": 1, "health": 1}
    assert by_start[(this_monday - timedelta(days=7)).isoformat()] == {"work": 1}
    assert out["tagged_entries"] == 2


def test_attention_mix_filters_soft_deleted_entries():
    fake = _FakeSupabase({"entries": [], "entry_tags": []})
    with patch.object(svc, "supabase", fake):
        asyncio.run(svc.get_attention_mix("user-1"))
    assert ("is_", ("deleted_at", "null")) in fake.calls["entries"]
    assert ("eq", ("user_id", "user-1")) in fake.calls["entries"]


def test_attention_mix_empty_is_quiet_not_crash():
    fake = _FakeSupabase({"entries": [], "entry_tags": []})
    with patch.object(svc, "supabase", fake):
        out = asyncio.run(svc.get_attention_mix("user-1"))
    assert out["tagged_entries"] == 0
    assert all(w["counts"] == {} for w in out["weeks"])


# ── Service-level: gravity aggregation ────────────────────────────────────────


def _entry(i, days_ago):
    return {
        "id": i,
        "created_at": (
            datetime.now(timezone.utc) - timedelta(days=days_ago, hours=6)
        ).isoformat(),
    }


def test_gravity_shares_current_vs_prior_window_top5():
    # Current window (0-30d): 10 entries. Prior (30-60d): 5 entries.
    entries = [_entry(i, 2) for i in range(1, 11)] + [_entry(i, 40) for i in range(11, 16)]
    links = []
    # Entity A: 4/10 current, 1/5 prior. B: 2/10 current only.
    for eid in (1, 2, 3, 4):
        links.append({"entry_id": eid, "entity_id": "A"})
    links.append({"entry_id": 11, "entity_id": "A"})
    for eid in (5, 6):
        links.append({"entry_id": eid, "entity_id": "B"})
    # Entities C..G: 1 current entry each -> 6 ranked entities, only top 5 kept.
    for eid, ent in zip((7, 8, 9, 10, 7), ("C", "D", "E", "F", "G")):
        links.append({"entry_id": eid, "entity_id": ent})

    names = [
        {"id": eid, "name": f"Entity {eid}", "entity_type": "person"}
        for eid in ("A", "B", "C", "D", "E", "F", "G")
    ]
    fake = _FakeSupabase(
        {"entries": entries, "entry_entities": links, "entities": names}
    )
    with patch.object(svc, "supabase", fake):
        out = asyncio.run(svc.get_gravity("user-1"))

    assert out["window_days"] == 30
    assert out["total_entries"] == 10
    assert out["prior_total_entries"] == 5
    assert len(out["entities"]) == 5
    top = out["entities"][0]
    assert top["entity_id"] == "A"
    assert top["name"] == "Entity A"
    assert top["share"] == pytest.approx(0.4)
    assert top["prior_share"] == pytest.approx(0.2)
    second = out["entities"][1]
    assert second["entity_id"] == "B"
    assert second["share"] == pytest.approx(0.2)
    assert second["prior_share"] == 0
    shares = [e["share"] for e in out["entities"]]
    assert shares == sorted(shares, reverse=True)


def test_gravity_skips_entities_missing_from_user_scope():
    # A link whose entity_id has no row in the user's entities table (cross-user
    # or deleted entity) must be skipped, never rendered nameless.
    entries = [_entry(1, 2), _entry(2, 3)]
    links = [
        {"entry_id": 1, "entity_id": "mine"},
        {"entry_id": 2, "entity_id": "ghost"},
    ]
    names = [{"id": "mine", "name": "Mine", "entity_type": "project"}]
    fake = _FakeSupabase(
        {"entries": entries, "entry_entities": links, "entities": names}
    )
    with patch.object(svc, "supabase", fake):
        out = asyncio.run(svc.get_gravity("user-1"))
    ids = [e["entity_id"] for e in out["entities"]]
    assert ids == ["mine"]


def test_gravity_empty_no_division_by_zero():
    fake = _FakeSupabase({"entries": [], "entry_entities": [], "entities": []})
    with patch.object(svc, "supabase", fake):
        out = asyncio.run(svc.get_gravity("user-1"))
    assert out["entities"] == []
    assert out["total_entries"] == 0


def test_gravity_filters_soft_deleted_entries():
    fake = _FakeSupabase({"entries": [], "entry_entities": [], "entities": []})
    with patch.object(svc, "supabase", fake):
        asyncio.run(svc.get_gravity("user-1"))
    assert ("is_", ("deleted_at", "null")) in fake.calls["entries"]
    assert ("eq", ("user_id", "user-1")) in fake.calls["entries"]
