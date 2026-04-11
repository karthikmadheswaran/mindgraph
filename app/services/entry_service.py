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
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return {"entries": result.data}


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

    entry_id = skeleton.data[0]["id"] if skeleton.data else None
    state = build_entry_state(entry, user_id, str(entry_id) if entry_id else None)

    async def process_entry():
        try:
            async for event in workflow.astream(state, config=langfuse_config()):
                node_name = list(event.keys())[0]
                if entry_id:
                    supabase.table("entries").update(
                        {"pipeline_stage": node_name}
                    ).eq("id", entry_id).execute()

            await regenerate_insights_background(user_id)

        except Exception as e:
            logger.error("Background processing error: %s", e, exc_info=True)
            if entry_id:
                supabase.table("entries").update(
                    {
                        "status": "error",
                        "pipeline_stage": None,
                    }
                ).eq("id", entry_id).execute()

    background_tasks.add_task(process_entry)

    return {
        "status": "processing",
        "entry_id": entry_id,
        "message": "Your entry is being processed. Check the dashboard in a few seconds.",
    }


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
