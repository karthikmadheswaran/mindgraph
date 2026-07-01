import json
from datetime import datetime, timezone

from app.db import supabase


async def get_insights(user_id: str) -> dict:
    result = (
        supabase.table("insights")
        .select("id, insight_type, content, severity, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    return {"insights": result.data or []}


async def get_weekly(user_id: str) -> dict:
    result = (
        supabase.table("insights")
        .select("content, created_at")
        .eq("user_id", user_id)
        .eq("insight_type", "weekly_digest")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return {"status": "ok", "data": json.loads(result.data[0]["content"])}
    return {"status": "ok", "data": None}


async def get_patterns(user_id: str) -> dict:
    result = (
        supabase.table("insights")
        .select("content, created_at")
        .eq("user_id", user_id)
        .eq("insight_type", "pattern")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return {"status": "ok", "data": json.loads(result.data[0]["content"])}
    return {"status": "ok", "data": None}


async def get_forgotten(user_id: str) -> dict:
    result = (
        supabase.table("insights")
        .select("content, created_at")
        .eq("user_id", user_id)
        .eq("insight_type", "forgotten_projects")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return {"status": "ok", "data": json.loads(result.data[0]["content"])}
    return {"status": "ok", "data": None}


# --- Reflection self-synthesis (the "gift") ---
# Reads the evolving per-user self-understanding doc written by app/synthesis_engine.
# `opened`/`opened_at` drive the gift UX: null opened_at => wrapped (unopened).

async def get_synthesis(user_id: str) -> dict:
    result = (
        supabase.table("user_synthesis")
        .select("synthesis_text, generated_at, opened_at, updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    row = result.data[0] if result.data else None
    if not row or not (row.get("synthesis_text") or "").strip():
        return {"status": "ok", "data": None}
    return {
        "status": "ok",
        "data": {
            "synthesis_text": row["synthesis_text"],
            "generated_at": row.get("generated_at"),
            "opened_at": row.get("opened_at"),
            "opened": bool(row.get("opened_at")),
        },
    }


async def mark_synthesis_opened(user_id: str) -> dict:
    """Stamp opened_at once (first reveal). Idempotent — a re-open keeps the original
    time, and a later regeneration re-wraps by resetting opened_at to null."""
    result = (
        supabase.table("user_synthesis")
        .select("opened_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"status": "not_found"}
    if result.data[0].get("opened_at"):
        return {"status": "already_opened", "opened_at": result.data[0]["opened_at"]}

    now = datetime.now(timezone.utc).isoformat()
    (
        supabase.table("user_synthesis")
        .update({"opened_at": now})
        .eq("user_id", user_id)
        .execute()
    )
    return {"status": "opened", "opened_at": now}
