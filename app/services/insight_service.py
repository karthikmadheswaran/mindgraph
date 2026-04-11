import json

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
