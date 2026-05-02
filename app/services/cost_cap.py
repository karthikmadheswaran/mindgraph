import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db import supabase

logger = logging.getLogger(__name__)

TIER_CAPS: dict[str, Decimal] = {
    "free": Decimal("0.10"),
    "pro": Decimal("1.00"),
}
ESTIMATES: dict[str, Decimal] = {
    "entry": Decimal("0.003"),
    "ask": Decimal("0.0008"),
}


async def check_cost_cap(user_id: str, tier: str) -> None:
    """Raise HTTP 429 if the user has hit their daily LLM cost cap."""
    from fastapi import HTTPException

    cap = TIER_CAPS.get(tier, TIER_CAPS["free"])
    today = datetime.now(timezone.utc).date().isoformat()
    result = (
        supabase.from_("daily_llm_costs")
        .select("cost_usd")
        .eq("user_id", user_id)
        .eq("date", today)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    spent = Decimal(str(rows[0].get("cost_usd", "0"))) if rows else Decimal("0")
    if spent >= cap:
        raise HTTPException(
            status_code=429,
            detail=f"Daily LLM cost cap reached (${cap}). Resets at midnight UTC.",
            headers={"Retry-After": _seconds_until_midnight(), "X-Cost-Cap": str(cap)},
        )


async def record_cost(
    user_id: str, request_type: str, trace_id: str | None = None
) -> None:
    """Upsert LLM cost for today. Tries Langfuse trace; falls back to fixed estimate."""
    cost = await _fetch_langfuse_cost(trace_id) if trace_id else None
    if not cost:
        cost = ESTIMATES.get(request_type, ESTIMATES["ask"])
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        supabase.rpc(
            "increment_daily_cost",
            {"p_user_id": user_id, "p_date": today, "p_cost": float(cost)},
        ).execute()
    except Exception as e:
        logger.warning("increment_daily_cost RPC failed for %s: %s", user_id, e)


async def _fetch_langfuse_cost(trace_id: str) -> Decimal | None:
    """Try to get actual LLM cost from Langfuse. Returns None if unavailable."""
    try:
        from langfuse import Langfuse

        client = Langfuse()
        client.flush()
        await asyncio.sleep(3)
        trace = client.fetch_trace(trace_id)
        if trace and trace.data:
            total = sum(
                float(obs.total_cost or 0)
                for obs in (trace.data.observations or [])
            )
            if total > 0:
                return Decimal(str(total))
    except Exception as e:
        logger.warning("Langfuse cost fetch failed for trace %s: %s", trace_id, e)
    return None


def _seconds_until_midnight() -> str:
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return str(int((midnight - now).total_seconds()))
