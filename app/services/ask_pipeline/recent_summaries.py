from datetime import datetime, timezone

from app.db import supabase
from app.services.ask_pipeline.date_format import format_entry_date
from app.services.ask_pipeline.state import AskState


async def recent_summaries(state: AskState) -> dict:
    """Always-on baseline context: last 5 completed entries."""
    now = datetime.now(timezone.utc)
    result = (
        supabase.table("entries")
        .select("auto_title, summary, created_at")
        .eq("user_id", state["user_id"])
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )

    rows = result.data or []
    summaries = [
        {
            "date": format_entry_date(row["created_at"], now),
            "title": (row.get("auto_title") or "Untitled").strip(),
            "summary": (row.get("summary") or "").strip(),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {"recent_summaries": summaries}
