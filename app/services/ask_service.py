import logging
from datetime import datetime, timezone

from app.ask_memory import (
    build_ask_prompt,
    build_compaction_prompt,
    format_conversation_messages,
)
from app.db import supabase
from app.embeddings import get_embedding
from app.llm import extract_text, flash as model
from app.services.observability import langfuse_config

logger = logging.getLogger(__name__)


async def compact_old_messages(user_id: str):
    """
    Background task: if user has >20 messages in ask_messages,
    compact the oldest messages (keeping the 10 most recent) into user_memory.
    Then delete the compacted messages.
    """
    try:
        count_result = (
            supabase.table("ask_messages")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        total_count = count_result.count

        if total_count is None or total_count <= 20:
            return

        all_result = (
            supabase.table("ask_messages")
            .select("id, role, content, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        all_messages = all_result.data or []

        messages_to_compact = all_messages[:-10]
        if not messages_to_compact:
            return

        memory_result = (
            supabase.table("user_memory")
            .select("memory_text")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        existing_memory = ""
        if memory_result.data:
            existing_memory = memory_result.data[0].get("memory_text", "")

        conversation_text = format_conversation_messages(messages_to_compact)
        compaction_prompt = build_compaction_prompt(existing_memory, conversation_text)

        response = await model.ainvoke(
            compaction_prompt,
            config=langfuse_config(),
        )
        new_memory = extract_text(response)

        (
            supabase.table("user_memory")
            .upsert(
                {
                    "user_id": user_id,
                    "memory_text": new_memory,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="user_id",
            )
            .execute()
        )

        ids_to_delete = [msg["id"] for msg in messages_to_compact]
        if ids_to_delete:
            supabase.table("ask_messages").delete().in_("id", ids_to_delete).execute()

    except Exception as exc:
        logger.error(
            "Compact old messages failed for user %s: %s",
            user_id,
            exc,
            exc_info=True,
        )


async def get_history(user_id: str) -> dict:
    result = (
        supabase.table("ask_messages")
        .select("role, content, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    messages = list(reversed(result.data)) if result.data else []
    return {"messages": messages}


async def get_memory(user_id: str) -> dict:
    result = (
        supabase.table("user_memory")
        .select("memory_text, updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"memory": None, "updated_at": None}

    row = result.data[0]
    return {
        "memory": row.get("memory_text", ""),
        "updated_at": row.get("updated_at"),
    }


async def ask(question: str, user_id: str) -> str:
    history_result = (
        supabase.table("ask_messages")
        .select("role, content")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    history_messages = list(reversed(history_result.data)) if history_result.data else []
    conversation_history = format_conversation_messages(history_messages)

    memory_result = (
        supabase.table("user_memory")
        .select("memory_text")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    user_memory = ""
    if memory_result.data:
        user_memory = memory_result.data[0].get("memory_text", "")

    query_embedding = await get_embedding(question)
    result = supabase.rpc(
        "match_entries",
        {
            "query_embedding": query_embedding,
            "match_count": 5,
            "filter_user_id": user_id,
        },
    ).execute()

    context_text = ""
    if result.data:
        formatted_entries = []
        for i, entry in enumerate(result.data, 1):
            date = entry.get("created_at", "Unknown date")
            title = entry.get("auto_title", "No title")
            formatted_entries.append(
                f"Entry {i} (created at {date}, title: {title}):\n{entry['cleaned_text']}"
            )
        context_text = "\n\n---\n\n".join(formatted_entries)

    prompt = build_ask_prompt(
        question=question,
        user_memory=user_memory,
        conversation_history=conversation_history,
        context_text=context_text,
    )

    response = await model.ainvoke(prompt, config=langfuse_config())
    answer = extract_text(response)

    supabase.table("ask_messages").insert(
        [
            {
                "user_id": user_id,
                "role": "user",
                "content": question,
            },
            {
                "user_id": user_id,
                "role": "assistant",
                "content": answer,
            },
        ]
    ).execute()

    return answer
