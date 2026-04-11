import logging

from fastapi import BackgroundTasks, HTTPException

from app.db import supabase
from app.schemas import EntryRequest
from app.services import ask_service, entry_service

logger = logging.getLogger(__name__)


def _normalize_message(row: dict) -> dict:
    message = dict(row)
    message["metadata"] = message.get("metadata") or {}
    message["entry_id"] = message.get("entry_id")
    return message


def _insert_message(
    user_id: str,
    role: str,
    content: str,
    metadata: dict | None = None,
    entry_id: str | None = None,
) -> dict:
    payload = {
        "user_id": user_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
    }
    if entry_id:
        payload["entry_id"] = entry_id

    result = supabase.table("ask_messages").insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to store message")

    return _normalize_message(result.data[0])


def _validate_content(content: str) -> str:
    value = str(content or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail="Message content is required")
    return value


async def get_messages(
    user_id: str,
    limit: int = 20,
    before: str | None = None,
) -> list[dict]:
    limit = max(1, min(limit, 50))
    query = (
        supabase.table("ask_messages")
        .select("id, user_id, role, content, created_at, metadata, entry_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
    )

    if before:
        query = query.lt("created_at", before)

    result = query.execute()
    return [_normalize_message(row) for row in (result.data or [])]


async def send_ask_message(user_id: str, content: str) -> dict:
    content = _validate_content(content)
    user_message = _insert_message(user_id, "user", content)

    try:
        answer = await ask_service.generate_answer(
            content,
            user_id,
            exclude_message_id=user_message["id"],
        )
        assistant_message = _insert_message(user_id, "assistant", answer)
    except Exception as exc:
        logger.error("Ask conversation message failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate answer") from exc

    return {"messages": [user_message, assistant_message]}


async def send_journal_message(
    user_id: str,
    content: str,
    background_tasks: BackgroundTasks,
) -> dict:
    content = _validate_content(content)
    journal_message = _insert_message(
        user_id,
        "journal_entry",
        content,
        metadata={"pipeline_stage": "queued"},
    )

    try:
        entry = EntryRequest(raw_text=content)
        await entry_service.enqueue_entry_processing(
            entry,
            background_tasks,
            user_id,
            conversation_message_id=journal_message["id"],
        )
    except Exception as exc:
        logger.error("Journal conversation message failed: %s", exc, exc_info=True)
        supabase.table("ask_messages").update(
            {
                "metadata": {
                    "pipeline_stage": "error",
                    "error": str(exc),
                }
            }
        ).eq("id", journal_message["id"]).execute()
        raise HTTPException(
            status_code=500,
            detail="Failed to queue journal entry",
        ) from exc

    return {"messages": [journal_message]}


async def get_message_status(message_id: str, user_id: str) -> dict:
    result = (
        supabase.table("ask_messages")
        .select("id, metadata, entry_id")
        .eq("id", message_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Message not found")

    row = _normalize_message(result.data[0])
    return {
        "id": row["id"],
        "metadata": row.get("metadata") or {},
        "entry_id": row.get("entry_id"),
    }
