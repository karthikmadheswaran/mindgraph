from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

from app.auth import get_current_user
from app.db import supabase
from app.services.tier_service import tier_service

# (limit, window_str) per endpoint per tier
LIMITS: dict[str, dict[str, tuple[int, str]]] = {
    "free": {"entries": (5, "7d"), "asks": (20, "1d")},
    "pro": {"entries": (100, "1d"), "asks": (200, "1d")},
}
IP_LIMIT = 30
IP_WINDOW_STR = "1h"

_WINDOW_DELTA: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
}


def _parse_window(window_str: str) -> timedelta:
    return _WINDOW_DELTA.get(window_str, timedelta(days=1))


def _window_start(window_str: str) -> datetime:
    now = datetime.now(timezone.utc)
    if window_str == "1h":
        return now.replace(minute=0, second=0, microsecond=0)
    if window_str == "1d":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if window_str == "7d":
        # Monday of the current ISO week
        return (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _retry_after(ws: datetime, window_str: str) -> str:
    delta = _parse_window(window_str)
    secs = int((ws + delta - datetime.now(timezone.utc)).total_seconds())
    return str(max(secs, 0))


def _try_rate_limit(key: str, ws: datetime, limit: int) -> bool:
    """Calls the atomic try_rate_limit DB function. Returns True if allowed."""
    result = supabase.rpc(
        "try_rate_limit",
        {"p_key": key, "p_window_start": ws.isoformat(), "p_limit": limit},
    ).execute()
    return bool(result.data)


async def entry_rate_limit(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> None:
    # IP-level guard (applies regardless of tier)
    ip = request.client.host if request.client else "unknown"
    ip_ws = _window_start(IP_WINDOW_STR)
    if not _try_rate_limit(f"ip:{ip}:all", ip_ws, IP_LIMIT):
        raise HTTPException(
            status_code=429,
            detail="Too many requests from this IP address.",
            headers={"Retry-After": _retry_after(ip_ws, IP_WINDOW_STR)},
        )

    # User tier-based limit
    tier = await tier_service.get_user_tier(user_id)
    limit, window_str = LIMITS.get(tier, LIMITS["free"])["entries"]
    ws = _window_start(window_str)
    if not _try_rate_limit(f"user:{user_id}:entries", ws, limit):
        raise HTTPException(
            status_code=429,
            detail=f"Entry limit reached ({limit} per {window_str}). Upgrade to Pro for higher limits.",
            headers={
                "Retry-After": _retry_after(ws, window_str),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Tier": tier,
            },
        )


async def ask_rate_limit(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> None:
    # IP-level guard
    ip = request.client.host if request.client else "unknown"
    ip_ws = _window_start(IP_WINDOW_STR)
    if not _try_rate_limit(f"ip:{ip}:all", ip_ws, IP_LIMIT):
        raise HTTPException(
            status_code=429,
            detail="Too many requests from this IP address.",
            headers={"Retry-After": _retry_after(ip_ws, IP_WINDOW_STR)},
        )

    # User tier-based limit
    tier = await tier_service.get_user_tier(user_id)
    limit, window_str = LIMITS.get(tier, LIMITS["free"])["asks"]
    ws = _window_start(window_str)
    if not _try_rate_limit(f"user:{user_id}:asks", ws, limit):
        raise HTTPException(
            status_code=429,
            detail=f"Ask limit reached ({limit} per {window_str}). Upgrade to Pro for higher limits.",
            headers={
                "Retry-After": _retry_after(ws, window_str),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Tier": tier,
            },
        )
