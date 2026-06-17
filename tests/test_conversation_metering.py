"""Regression tests locking the conversation-route metering fix.

Original bug (STATE Critical #2): POST /conversations/messages in *ask* mode
called conversation.send_ask_message -> ask_service.generate_answer directly,
bypassing ask_service.ask() — the only place record_cost ran. So ask-mode
was triply unmetered: no rate limit, no cost cap, no cost recording. Nothing
tested this path, which is exactly why it regressed silently.

These tests drive the real FastAPI route through TestClient (so http_request:
Request is injected for real, proving the in-handler IP guard is threaded
correctly) and lock:
  1. ask-mode records cost AND the per-IP guard fires in-handler
  2. ask-mode enforces the daily cost cap (429, answer never generated)
  3. a "paid" user resolves to the "pro" tier -> pro limits, not free

All DB / Redis / LLM calls are mocked; no network needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.main import app
from app.services.tier_service import TierService, tier_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(role: str) -> dict:
    """A fully-formed ask_messages row that satisfies MessageResponse."""
    return {
        "id": f"m-{role}",
        "user_id": "test-uid",
        "role": role,
        "content": "x",
        "created_at": "2026-06-15T00:00:00Z",
        "metadata": {},
        "entry_id": None,
    }


def _select_result(rows: list):
    """Mock supabase .from_().select()...execute() chain yielding rows."""
    result = MagicMock()
    result.data = rows
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = result
    return chain


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: "test-uid"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# 1. ask-mode records cost AND the IP guard fires in-handler
# ---------------------------------------------------------------------------


def test_ask_mode_records_cost_and_ip_guard_fires(client):
    rpc_calls = []

    def rpc_side_effect(name, params=None, *a, **k):
        rpc_calls.append((name, params or {}))
        r = MagicMock()
        r.data = True  # allow every rate-limit check
        chain = MagicMock()
        chain.execute.return_value = r
        return chain

    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        tier_service, "get_user_tier", AsyncMock(return_value="free")
    ), patch("app.services.cost_cap.supabase") as cc_sb, patch(
        "app.services.conversation.ask_service.generate_answer",
        AsyncMock(return_value="an answer"),
    ), patch(
        "app.services.conversation._insert_message",
        side_effect=lambda user_id, role, *a, **k: _msg(role),
    ), patch(
        "app.services.cost_cap.record_cost", new_callable=AsyncMock
    ) as rec:
        rl_sb.rpc.side_effect = rpc_side_effect
        cc_sb.from_.return_value = _select_result([])  # no spend today -> under cap

        resp = client.post(
            "/conversations/messages", json={"content": "hello", "mode": "ask"}
        )

    assert resp.status_code == 200
    # The core regression: ask-mode MUST record cost (it never did before).
    rec.assert_awaited_once_with("test-uid", "ask")
    # The IP guard (ip:<host>:all) must have fired from inside the handler,
    # confirming http_request: Request is threaded into ask_rate_limit.
    ip_keys = [
        p.get("p_key", "")
        for _, p in rpc_calls
        if str(p.get("p_key", "")).startswith("ip:")
    ]
    assert ip_keys, f"IP guard rpc never fired; rpc calls were {rpc_calls}"


# ---------------------------------------------------------------------------
# 2. ask-mode enforces the cost cap (429, answer never generated)
# ---------------------------------------------------------------------------


def test_ask_mode_enforces_cost_cap_429(client):
    def rpc_allow(name, params=None, *a, **k):
        r = MagicMock()
        r.data = True  # rate-limit checks pass; the cap is what blocks
        chain = MagicMock()
        chain.execute.return_value = r
        return chain

    with patch("app.dependencies.rate_limit.supabase") as rl_sb, patch.object(
        tier_service, "get_user_tier", AsyncMock(return_value="free")
    ), patch("app.services.cost_cap.supabase") as cc_sb, patch(
        "app.services.cost_cap.track"
    ), patch(
        "app.services.conversation.send_ask_message", new_callable=AsyncMock
    ) as send_ask:
        rl_sb.rpc.side_effect = rpc_allow
        # Already at the free cap ($0.10) for today.
        cc_sb.from_.return_value = _select_result([{"cost_usd": "0.10"}])

        resp = client.post(
            "/conversations/messages", json={"content": "hello", "mode": "ask"}
        )

    assert resp.status_code == 429
    assert "cost cap" in resp.json()["detail"].lower()
    # The cap must gate BEFORE any answer is generated.
    send_ask.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. "paid" resolves to "pro" -> pro limits, not free
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_paid_tier_resolves_to_pro_db_path():
    """DB row subscription_tier='paid' must surface as the internal 'pro'."""
    service = TierService()  # fresh instance, no Redis env -> hits DB path

    with patch.object(service, "_redis_client", return_value=None), patch(
        "app.services.tier_service.supabase"
    ) as mock_sb:
        mock_sb.from_.return_value = _select_result([{"subscription_tier": "paid"}])
        tier = await service.get_user_tier("test-uid")

    assert tier == "pro"


@pytest.mark.anyio
async def test_paid_tier_resolves_to_pro_cache_path():
    """A cached 'paid' value must also normalize to 'pro' without a DB hit."""
    service = TierService()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="paid")

    with patch.object(service, "_redis_client", return_value=mock_redis), patch(
        "app.services.tier_service.supabase"
    ) as mock_sb:
        tier = await service.get_user_tier("test-uid")

    assert tier == "pro"
    mock_sb.from_.assert_not_called()


def test_pro_tier_gets_pro_ask_limit_not_free():
    """The resolved 'pro' tier must key into pro ask limits, not free."""
    from app.dependencies.rate_limit import LIMITS

    resolved = "pro"  # what a 'paid' user now resolves to (tests above)
    pro_limit = LIMITS[resolved]["asks"][0]
    free_limit = LIMITS["free"]["asks"][0]

    assert pro_limit == 200
    assert pro_limit != free_limit
