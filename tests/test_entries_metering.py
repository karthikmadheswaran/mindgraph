"""Hermetic tests locking metering on POST /entries and POST /entries/stream.

Both routes were carved out of the 15/06 metering PR (#5) as a logged follow-up
and stayed UNMETERED (no rate limit, no cost cap). They now mirror /entries/async
exactly: entry_rate_limit (dependency, fires before the body) + check_cost_cap
(before the work). For /stream the checks fire BEFORE create_entry_stream is
called, so a limit/cap hit returns a clean 429 and the stream never opens.

All DB / Redis / LLM mocked; the real routes are driven via TestClient.
"""
import os

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.services.tier_service import tier_service

_VALID_ENTRY = {
    "auto_title": "t",
    "summary": "s",
    "classifier": [],
    "core_entities": [],
    "deadline": [],
}


def _cost_rows(rows):
    """Mock supabase.from_("daily_llm_costs").select()...execute() -> rows."""
    result = MagicMock()
    result.data = rows
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = result
    return chain


def _rl(allow_user=True):
    """try_rate_limit rpc side-effect: IP guard always allowed; the user-entries
    limit allowed/denied per allow_user (so we exercise the user limit, not IP)."""
    def side_effect(name, params=None, *a, **k):
        key = str((params or {}).get("p_key", ""))
        r = MagicMock()
        r.data = allow_user if key.startswith("user:") else True
        chain = MagicMock()
        chain.execute.return_value = r
        return chain
    return side_effect


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: "test-uid"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _run(client, route, service_attr, rl_allow_user, cost_rows, ret):
    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch(
        "app.dependencies.rate_limit.track"
    ), patch.object(
        tier_service, "get_user_tier", AsyncMock(return_value="free")
    ), patch(
        "app.services.cost_cap.supabase"
    ) as cc_sb, patch(
        "app.services.cost_cap.track"
    ), patch(
        "app.main.track"
    ), patch(
        f"app.services.entry_service.{service_attr}", new_callable=AsyncMock
    ) as svc:
        rl_sb.rpc.side_effect = _rl(allow_user=rl_allow_user)
        cc_sb.from_.return_value = _cost_rows(cost_rows)
        svc.return_value = ret
        resp = client.post(route, json={"raw_text": "hello"})
        return resp, svc


# ── POST /entries ─────────────────────────────────────────────────────────


def test_entries_rate_limit_429(client):
    resp, svc = _run(client, "/entries", "create_entry", False, [], _VALID_ENTRY)
    assert resp.status_code == 429
    assert "limit" in resp.json()["detail"].lower()
    svc.assert_not_awaited()  # gated before the work


def test_entries_cost_cap_429(client):
    resp, svc = _run(client, "/entries", "create_entry", True, [{"cost_usd": "0.10"}], _VALID_ENTRY)
    assert resp.status_code == 429
    assert "cost cap" in resp.json()["detail"].lower()
    svc.assert_not_awaited()  # cap gates before the work


def test_entries_under_limits_proceeds(client):
    resp, svc = _run(client, "/entries", "create_entry", True, [], _VALID_ENTRY)
    assert resp.status_code == 200
    svc.assert_awaited_once()


# ── POST /entries/stream (checks must fire BEFORE the stream opens) ─────────


def test_entries_stream_rate_limit_429_no_partial_stream(client):
    resp, svc = _run(client, "/entries/stream", "create_entry_stream", False, [], {"ok": True})
    assert resp.status_code == 429
    assert "limit" in resp.json()["detail"].lower()
    svc.assert_not_awaited()  # the StreamingResponse was never constructed


def test_entries_stream_cost_cap_429_no_partial_stream(client):
    resp, svc = _run(client, "/entries/stream", "create_entry_stream", True, [{"cost_usd": "0.10"}], {"ok": True})
    assert resp.status_code == 429
    assert "cost cap" in resp.json()["detail"].lower()
    svc.assert_not_awaited()  # cap gates before the stream opens


def test_entries_stream_under_limits_opens(client):
    resp, svc = _run(client, "/entries/stream", "create_entry_stream", True, [], {"ok": True})
    assert resp.status_code == 200
    svc.assert_awaited_once()  # the stream path actually ran
