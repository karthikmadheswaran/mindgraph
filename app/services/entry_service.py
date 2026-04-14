import json
import logging

from fastapi import BackgroundTasks
from fastapi.responses import StreamingResponse

from app.db import supabase
from app.embeddings import get_embedding
from app.graph import build_graph
from app.insights_engine import regenerate_insights_background
from app.retrieval import advanced_search
from app.schemas import EntryRequest, EntryResponse
from app.services.observability import langfuse_config

logger = logging.getLogger(__name__)

workflow = build_graph()


def build_entry_state(
    entry: EntryRequest,
    user_id: str,
    entry_id: str | None = None,
) -> dict:
    state = {
        "raw_text": entry.raw_text,
        "user_id": user_id,
        "user_timezone": entry.user_timezone,
        "input_type": entry.input_type,
        "cleaned_text": "",
        "auto_title": "",
        "summary": "",
        "attachment_url": "",
        "classifier": [],
        "core_entities": [],
        "deadline": [],
        "relations": [],
        "trigger_check": False,
        "duplicate_of": None,
        "dedup_check_result": None,
    }
    if entry_id is not None:
        state["entry_id"] = entry_id
    return state


def _serialize_deadline(deadline: dict) -> dict:
    return {
        "description": deadline.get("description", ""),
        "due_date": str(deadline.get("due_date", deadline.get("due_at", ""))),
    }


def _serialize_entity(entity: dict) -> dict:
    return {
        "name": entity.get("name", ""),
        "type": entity.get("entity_type", entity.get("type", "")),
    }


def _conversation_metadata_from_pipeline(final_result: dict, pipeline_stage: str) -> dict:
    metadata = {"pipeline_stage": pipeline_stage}

    if "auto_title" in final_result:
        metadata["auto_title"] = final_result.get("auto_title", "")
    if "summary" in final_result:
        metadata["summary"] = final_result.get("summary", "")
    if "core_entities" in final_result:
        metadata["entities"] = [
            _serialize_entity(entity)
            for entity in final_result.get("core_entities", [])
            if isinstance(entity, dict)
        ]
    if "deadline" in final_result:
        metadata["deadlines"] = [
            _serialize_deadline(deadline)
            for deadline in final_result.get("deadline", [])
            if isinstance(deadline, dict)
        ]
    if "classifier" in final_result:
        metadata["categories"] = final_result.get("classifier", [])

    return metadata


def _update_conversation_message(
    message_id: str,
    entry_id: str | None,
    metadata: dict,
) -> None:
    update_data = {"metadata": metadata}
    if entry_id:
        update_data["entry_id"] = entry_id

    (
        supabase.table("ask_messages")
        .update(update_data)
        .eq("id", message_id)
        .execute()
    )


def _fetch_entry_entities(entry_id: str, user_id: str) -> list[dict]:
    link_result = (
        supabase.table("entry_entities")
        .select("entity_id")
        .eq("entry_id", entry_id)
        .execute()
    )
    entity_ids = [
        row["entity_id"]
        for row in (link_result.data or [])
        if row.get("entity_id")
    ]
    if not entity_ids:
        return []

    entity_result = (
        supabase.table("entities")
        .select("id, name, entity_type")
        .eq("user_id", user_id)
        .in_("id", entity_ids)
        .execute()
    )
    return [_serialize_entity(entity) for entity in (entity_result.data or [])]


def _fetch_entry_deadlines(entry_id: str, user_id: str) -> list[dict]:
    result = (
        supabase.table("deadlines")
        .select("description, due_date")
        .eq("user_id", user_id)
        .eq("source_entry_id", entry_id)
        .order("due_date", desc=False)
        .execute()
    )
    return [_serialize_deadline(deadline) for deadline in (result.data or [])]


def _fetch_entry_categories(entry_id: str) -> list[str]:
    result = (
        supabase.table("entry_tags")
        .select("category")
        .eq("entry_id", entry_id)
        .execute()
    )
    return [
        row["category"]
        for row in (result.data or [])
        if row.get("category")
    ]


def _build_completed_conversation_metadata(
    entry_id: str,
    user_id: str,
    final_result: dict,
) -> dict:
    entry_result = (
        supabase.table("entries")
        .select("auto_title, summary")
        .eq("id", entry_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    entry_row = entry_result.data[0] if entry_result.data else {}

    categories = _fetch_entry_categories(entry_id) or final_result.get("classifier", [])

    return {
        "pipeline_stage": "completed",
        "auto_title": entry_row.get("auto_title", final_result.get("auto_title", "")),
        "summary": entry_row.get("summary", final_result.get("summary", "")),
        "entities": _fetch_entry_entities(entry_id, user_id),
        "deadlines": _fetch_entry_deadlines(entry_id, user_id),
        "categories": categories,
    }


def _insert_processing_entry(entry: EntryRequest, user_id: str):
    skeleton = supabase.table("entries").insert(
        {
            "raw_text": entry.raw_text,
            "user_id": user_id,
            "cleaned_text": "",
            "auto_title": "",
            "summary": "",
            "status": "processing",
            "pipeline_stage": "normalize",
        }
    ).execute()

    return skeleton.data[0]["id"] if skeleton.data else None


async def create_entry(entry: EntryRequest, user_id: str) -> EntryResponse:
    state = build_entry_state(entry, user_id)
    result = await workflow.ainvoke(state, config=langfuse_config())

    return EntryResponse(
        auto_title=result["auto_title"],
        summary=result["summary"],
        classifier=result["classifier"],
        core_entities=result["core_entities"],
        deadline=result["deadline"],
    )


async def list_entries(user_id: str) -> dict:
    result = (
        supabase.table("entries")
        .select("id, raw_text, cleaned_text, auto_title, summary, created_at, status, pipeline_stage")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return {"entries": result.data}


async def soft_delete_entry(entry_id: str, user_id: str) -> dict:
    from datetime import datetime, timezone
    from fastapi import HTTPException

    entry_result = (
        supabase.table("entries")
        .select("id, user_id, deleted_at")
        .eq("id", entry_id)
        .limit(1)
        .execute()
    )
    rows = entry_result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry_row = rows[0]
    if entry_row.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if entry_row.get("deleted_at") is not None:
        raise HTTPException(status_code=410, detail="Entry already deleted")

    link_rows = (
        supabase.table("entry_entities")
        .select("entity_id")
        .eq("entry_id", entry_id)
        .execute()
        .data
        or []
    )

    entity_decrements: dict[str, int] = {}
    for link in link_rows:
        eid = link.get("entity_id")
        if eid:
            entity_decrements[eid] = entity_decrements.get(eid, 0) + 1

    if entity_decrements:
        existing = (
            supabase.table("entities")
            .select("id, mention_count")
            .in_("id", list(entity_decrements.keys()))
            .execute()
            .data
            or []
        )
        for ent in existing:
            eid = ent["id"]
            new_count = max(0, (ent.get("mention_count") or 0) - entity_decrements[eid])
            (
                supabase.table("entities")
                .update({"mention_count": new_count})
                .eq("id", eid)
                .execute()
            )

    supabase.table("entry_entities").delete().eq("entry_id", entry_id).execute()
    supabase.table("entity_relations").delete().eq("source_entry_id", entry_id).execute()
    supabase.table("deadlines").delete().eq("source_entry_id", entry_id).execute()
    supabase.table("entry_tags").delete().eq("entry_id", entry_id).execute()

    (
        supabase.table("entries")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", entry_id)
        .execute()
    )

    await regenerate_insights_background(user_id)

    logger.info("Soft-deleted entry %s for user %s", entry_id, user_id)
    return {"status": "deleted", "entry_id": entry_id}


async def search_entries(query: str, user_id: str) -> dict:
    query_embedding = await get_embedding(query)
    result = supabase.rpc(
        "match_entries",
        {
            "query_embedding": query_embedding,
            "match_count": 5,
            "filter_user_id": user_id,
        },
    ).execute()

    return {"results": result.data}


async def advanced_search_entries(query: str, user_id: str) -> dict:
    results = await advanced_search(query, user_id, match_count=5)
    return {"results": results}


async def create_entry_stream(entry: EntryRequest, user_id: str):
    state = build_entry_state(entry, user_id)

    async def event_stream():
        final_result = {}
        try:
            async for event in workflow.astream(state, config=langfuse_config()):
                node_name = list(event.keys())[0]
                node_output = event[node_name]
                if node_output and isinstance(node_output, dict):
                    final_result.update(node_output)
                update = {"node": node_name, "status": "completed"}
                yield f"data: {json.dumps(update)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'node': 'error', 'message': str(e)})}\n\n"

        deadlines = final_result.get("deadline", [])
        serializable_deadlines = []
        for deadline in deadlines:
            serializable_deadlines.append(
                {
                    "description": deadline.get("description", ""),
                    "due_at": str(deadline.get("due_at", "")),
                    "raw_text": deadline.get("raw_text", ""),
                }
            )

        done_payload = {
            "node": "done",
            "result": {
                "auto_title": final_result.get("auto_title", ""),
                "summary": final_result.get("summary", ""),
                "classifier": final_result.get("classifier", []),
                "core_entities": final_result.get("core_entities", []),
                "deadline": serializable_deadlines,
            },
        }
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def create_entry_async(
    entry: EntryRequest,
    background_tasks: BackgroundTasks,
    user_id: str,
) -> dict:
    return await enqueue_entry_processing(entry, background_tasks, user_id)


async def enqueue_entry_processing(
    entry: EntryRequest,
    background_tasks: BackgroundTasks,
    user_id: str,
    conversation_message_id: str | None = None,
) -> dict:
    entry_id = _insert_processing_entry(entry, user_id)
    state = build_entry_state(entry, user_id, str(entry_id) if entry_id else None)
    background_tasks.add_task(
        process_entry_background,
        state,
        user_id,
        entry_id,
        conversation_message_id,
    )

    return {
        "status": "processing",
        "entry_id": entry_id,
        "message": "Your entry is being processed. Check the dashboard in a few seconds.",
    }


async def process_entry_background(
    state: dict,
    user_id: str,
    entry_id: str | None,
    conversation_message_id: str | None = None,
) -> None:
    final_result = {}
    message_metadata = {"pipeline_stage": "normalize"}

    try:
        if conversation_message_id:
            _update_conversation_message(
                conversation_message_id,
                str(entry_id) if entry_id else None,
                message_metadata,
            )

        async for event in workflow.astream(state, config=langfuse_config()):
            node_name = list(event.keys())[0]
            node_output = event[node_name]
            if node_output and isinstance(node_output, dict):
                final_result.update(node_output)

            if entry_id:
                supabase.table("entries").update(
                    {"pipeline_stage": node_name}
                ).eq("id", entry_id).execute()

            if conversation_message_id:
                message_metadata.update(
                    _conversation_metadata_from_pipeline(final_result, node_name)
                )
                _update_conversation_message(
                    conversation_message_id,
                    str(entry_id) if entry_id else None,
                    message_metadata,
                )

        await regenerate_insights_background(user_id)

        if conversation_message_id and entry_id:
            try:
                message_metadata = _build_completed_conversation_metadata(
                    str(entry_id),
                    user_id,
                    final_result,
                )
            except Exception as metadata_exc:
                logger.warning(
                    "Conversation metadata fetch failed for entry %s: %s",
                    entry_id,
                    metadata_exc,
                    exc_info=True,
                )
                message_metadata.update(
                    _conversation_metadata_from_pipeline(final_result, "completed")
                )
                message_metadata["pipeline_stage"] = "completed"

            _update_conversation_message(
                conversation_message_id,
                str(entry_id),
                message_metadata,
            )

    except Exception as e:
        logger.error("Background processing error: %s", e, exc_info=True)
        if entry_id:
            supabase.table("entries").update(
                {
                    "status": "error",
                    "pipeline_stage": None,
                }
            ).eq("id", entry_id).execute()

        if conversation_message_id:
            message_metadata["pipeline_stage"] = "error"
            message_metadata["error"] = str(e)
            _update_conversation_message(
                conversation_message_id,
                str(entry_id) if entry_id else None,
                message_metadata,
            )


async def get_entry_status(entry_id: str, user_id: str):
    result = (
        supabase.table("entries")
        .select("id, status, pipeline_stage")
        .eq("id", entry_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data
