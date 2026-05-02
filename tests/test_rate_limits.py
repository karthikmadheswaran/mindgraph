"""
Rate limit + cost cap unit tests.

All DB, Redis, and external calls are mocked — no real Supabase or Upstash
connection is needed to run these tests.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_supabase_rpc_result(data):
    """Return a mock supabase .rpc().execute() chain that yields data."""
    result = MagicMock()
    result.data = data
    rpc_chain = MagicMock()
    rpc_chain.execute.return_value = result
    return rpc_chain


def _make_supabase_select_result(rows: list):
    """Return a mock supabase .from_().select()...execute() chain."""
    result = MagicMock()
    result.data = rows
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = result
    return chain


# ---------------------------------------------------------------------------
# Test 1: free tier — 429 on 6th entry (try_rate_limit returns False)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_free_tier_entry_limit_429():
    """After 5 entries in the window, the 6th call must return 429."""
    from fastapi import HTTPException

    # try_rate_limit returns False (limit already hit)
    rpc_result = MagicMock()
    rpc_result.data = False

    with patch("app.dependencies.rate_limit.supabase") as mock_sb, patch(
        "app.dependencies.rate_limit.tier_service"
    ) as mock_tier:
        mock_tier.get_user_tier = AsyncMock(return_value="free")
        mock_sb.rpc.return_value.execute.return_value = rpc_result

        from app.dependencies.rate_limit import _try_rate_limit, _window_start, LIMITS

        ws = _window_start("7d")
        limit, window_str = LIMITS["free"]["entries"]
        allowed = _try_rate_limit(f"user:test-uid:entries", ws, limit)
        assert allowed is False


# ---------------------------------------------------------------------------
# Test 2: pro tier — 429 on 101st entry (try_rate_limit returns False)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pro_tier_entry_limit_429():
    """After 100 entries in the pro window, the 101st call must be blocked."""
    from fastapi import HTTPException

    rpc_result = MagicMock()
    rpc_result.data = False

    with patch("app.dependencies.rate_limit.supabase") as mock_sb, patch(
        "app.dependencies.rate_limit.tier_service"
    ) as mock_tier:
        mock_tier.get_user_tier = AsyncMock(return_value="pro")
        mock_sb.rpc.return_value.execute.return_value = rpc_result

        from app.dependencies.rate_limit import _try_rate_limit, _window_start, LIMITS

        ws = _window_start("1d")
        limit, window_str = LIMITS["pro"]["entries"]
        assert limit == 100
        allowed = _try_rate_limit(f"user:test-uid:entries", ws, limit)
        assert allowed is False


# ---------------------------------------------------------------------------
# Test 3: IP fallback — 429 on 31st request
# ---------------------------------------------------------------------------


def test_ip_fallback_limit_429():
    """IP rate limit: 31st request in the hour window must be blocked."""
    rpc_result = MagicMock()
    rpc_result.data = False  # 31st request → over IP_LIMIT=30

    with patch("app.dependencies.rate_limit.supabase") as mock_sb:
        mock_sb.rpc.return_value.execute.return_value = rpc_result

        from app.dependencies.rate_limit import _try_rate_limit, _window_start, IP_LIMIT, IP_WINDOW_STR

        ws = _window_start(IP_WINDOW_STR)
        allowed = _try_rate_limit("ip:127.0.0.1:all", ws, IP_LIMIT)
        assert allowed is False
        assert IP_LIMIT == 30


# ---------------------------------------------------------------------------
# Test 4: cost cap — 429 when daily cost >= $0.10 (free tier)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cost_cap_free_tier_429():
    """When daily_llm_costs.cost_usd == 0.10, check_cost_cap must raise 429."""
    from fastapi import HTTPException
    from app.services.cost_cap import check_cost_cap

    with patch("app.services.cost_cap.supabase") as mock_sb:
        mock_sb.from_.return_value = _make_supabase_select_result(
            [{"cost_usd": "0.10"}]
        )

        with pytest.raises(HTTPException) as exc_info:
            await check_cost_cap(user_id="test-uid", tier="free")

        assert exc_info.value.status_code == 429
        assert "cost cap" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Test 5: headers correctness on 429 from entry_rate_limit
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rate_limit_headers_on_429():
    """The 429 exception must carry Retry-After, X-RateLimit-Limit, X-RateLimit-Tier."""
    from fastapi import HTTPException, Request

    rpc_result = MagicMock()
    rpc_result.data = True   # IP check passes
    rpc_result_blocked = MagicMock()
    rpc_result_blocked.data = False  # user tier check fails

    call_count = 0

    def rpc_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        chain = MagicMock()
        # First call: IP check → allowed
        # Second call: user entry limit → blocked
        chain.execute.return_value = rpc_result if call_count == 1 else rpc_result_blocked
        return chain

    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock()
    mock_request.client.host = "127.0.0.1"

    with patch("app.dependencies.rate_limit.supabase") as mock_sb, patch(
        "app.dependencies.rate_limit.tier_service"
    ) as mock_tier:
        mock_sb.rpc.side_effect = rpc_side_effect
        mock_tier.get_user_tier = AsyncMock(return_value="free")

        from app.dependencies.rate_limit import entry_rate_limit

        with pytest.raises(HTTPException) as exc_info:
            await entry_rate_limit(request=mock_request, user_id="test-uid")

        headers = exc_info.value.headers
        assert "Retry-After" in headers
        assert "X-RateLimit-Limit" in headers
        assert headers["X-RateLimit-Limit"] == "5"
        assert "X-RateLimit-Tier" in headers
        assert headers["X-RateLimit-Tier"] == "free"
        assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Test 6: Redis cache hit — Supabase users table NOT queried
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_tier_cache_hit_skips_db():
    """When Redis returns a cached tier, the Supabase users table must not be queried."""
    from app.services.tier_service import TierService

    service = TierService()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="pro")
    mock_redis.set = AsyncMock()

    with patch.object(service, "_redis_client", return_value=mock_redis), patch(
        "app.services.tier_service.supabase"
    ) as mock_sb:
        tier = await service.get_user_tier("test-uid")

    assert tier == "pro"
    # Supabase must NOT have been called since Redis returned a hit
    mock_sb.from_.assert_not_called()
