import asyncio
import json
import logging
import os
import uuid

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

# Exclude dedup "orphan" rows from dashboard surfaces. A near-duplicate entry is
# left status=completed with empty cleaned_text + dispatch_payload.pipeline_version
# = "duplicate" (see app/nodes/dedup.py); those would otherwise render as blank
# cards and inflate entry counts. The is.null clause is REQUIRED to keep in-flight
# / pre-dispatch rows (null dispatch_payload) visible — verified read-only against
# prod: it preserves all 93 null-payload rows + 124 normal completed, drops only
# the 9 duplicate orphans. DISPLAY-only; the orphan row itself is untouched (the
# populate-from-matched-entry behavior is the logged next dedup item).
_EXCLUDE_DUPLICATE_ORPHANS = (
    "dispatch_payload->>pipeline_version.is.null,"
    "dispatch_payload->>pipeline_version.neq.duplicate"
)


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


_redis_client = None
_redis_attempted = False
_FILTER_OPTIONS_TTL = 60


def _get_redis():
    global _redis_client, _redis_attempted
    if _redis_attempted:
        return _redis_client
    _redis_attempted = True
    url = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    try:
        from upstash_redis.asyncio import Redis
        _redis_client = Redis(url=url, token=token)
        return _redis_client
    except Exception as exc:
        logger.warning("entry_service Redis unavailable: %s", exc)
        return None


async def get_filter_options(user_id: str) -> dict:
    redis = _get_redis()
    cache_key = f"filter_options:{user_id}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                raw = cached if isinstance(cached, str) else cached.decode()
                return json.loads(raw)
        except Exception as exc:
            logger.warning("filter_options Redis get failed: %s", exc)

    entry_rows = (
        supabase.table("entries")
        .select("id")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )
    entry_ids = [r["id"] for r in (entry_rows.data or [])]

    categories: list[str] = []
    if entry_ids:
        tag_rows = (
            supabase.table("entry_tags")
            .select("category")
            .in_("entry_id", entry_ids[:500])
            .execute()
        )
        categories = sorted({r["category"] for r in (tag_rows.data or []) if r.get("category")})

    person_rows = (
        supabase.table("entities")
        .select("name")
        .eq("user_id", user_id)
        .eq("entity_type", "person")
        .limit(100)
        .execute()
    )
    persons = sorted({r["name"] for r in (person_rows.data or []) if r.get("name")})

    result = {"mood": categories, "person": persons, "category": categories}

    if redis:
        try:
            await redis.set(cache_key, json.dumps(result), ex=_FILTER_OPTIONS_TTL)
        except Exception as exc:
            logger.warning("filter_options Redis set failed: %s", exc)

    return result


async def list_entries(
    user_id: str,
    page: int = 1,
    page_size: int = 10,
    mood: str | None = None,
    person: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
) -> dict:
    # Build a set of entry IDs to include when entity/category filters are active
    filter_ids: set[str] | None = None

    if person:
        ent_rows = (
            supabase.table("entities")
            .select("id")
            .eq("user_id", user_id)
            .ilike("name", f"%{person}%")
            .execute()
        )
        ent_ids = [r["id"] for r in (ent_rows.data or [])]
        if ent_ids:
            link_rows = (
                supabase.table("entry_entities")
                .select("entry_id")
                .in_("entity_id", ent_ids[:50])
                .execute()
            )
            ids = {r["entry_id"] for r in (link_rows.data or [])}
        else:
            ids = set()
        filter_ids = ids if filter_ids is None else filter_ids & ids

    target_category = category or mood
    if target_category:
        tag_rows = (
            supabase.table("entry_tags")
            .select("entry_id")
            .eq("category", target_category)
            .execute()
        )
        ids = {r["entry_id"] for r in (tag_rows.data or [])}
        filter_ids = ids if filter_ids is None else filter_ids & ids

    query = (
        supabase.table("entries")
        .select(
            "id, raw_text, cleaned_text, auto_title, summary, "
            "created_at, status, pipeline_stage, dispatch_payload",
            count="exact",
        )
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .or_(_EXCLUDE_DUPLICATE_ORPHANS)
        .order("created_at", desc=True)
    )

    if filter_ids is not None:
        if not filter_ids:
            return {"entries": [], "total_count": 0, "page": page, "page_size": page_size}
        query = query.in_("id", list(filter_ids)[:200])

    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)
    if search:
        query = query.ilike("raw_text", f"%{search}%")

    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    result = query.execute()
    total_count = result.count if result.count is not None else len(result.data or [])

    return {
        "entries": result.data or [],
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
    }


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
    query_embedding = await get_embedding(query, task_type="RETRIEVAL_QUERY")
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
    from app.db import maybe_update_user_timezone
    await maybe_update_user_timezone(user_id, entry.user_timezone)
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
    trace_id = str(uuid.uuid4())

    try:
        if conversation_message_id:
            _update_conversation_message(
                conversation_message_id,
                str(entry_id) if entry_id else None,
                message_metadata,
            )

        async for event in workflow.astream(
            state, config=langfuse_config(trace_id=trace_id, user_id=user_id)
        ):
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

        from app.services.cost_cap import record_cost

        asyncio.create_task(record_cost(user_id, "entry", trace_id=trace_id))

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
    # DEBUG: run both an explicit-column select and a select(*) to identify whether
    # PostgREST/supabase-py is dropping dispatch_payload on the explicit form.
    explicit = (
        supabase.table("entries")
        .select("id, status, pipeline_stage, dispatch_payload")
        .eq("id", entry_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    star = (
        supabase.table("entries")
        .select("*")
        .eq("id", entry_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    e_data = explicit.data or {}
    s_data = star.data or {}
    e_dp = e_data.get("dispatch_payload")
    s_dp = s_data.get("dispatch_payload")

    logger.info(
        "get_entry_status: entry=%s | explicit dp_type=%s isnull=%s len=%s | star dp_type=%s isnull=%s len=%s",
        entry_id,
        type(e_dp).__name__, e_dp is None,
        len(e_dp) if isinstance(e_dp, (str, dict, list)) else "-",
        type(s_dp).__name__, s_dp is None,
        len(s_dp) if isinstance(s_dp, (str, dict, list)) else "-",
    )

    # Prefer whichever has the payload. Falls back gracefully if both are null.
    data = {
        "id": e_data.get("id") or s_data.get("id"),
        "status": e_data.get("status") or s_data.get("status"),
        "pipeline_stage": e_data.get("pipeline_stage") if "pipeline_stage" in e_data else s_data.get("pipeline_stage"),
        "dispatch_payload": e_dp if e_dp is not None else s_dp,
    }

    dp = data.get("dispatch_payload")
    if isinstance(dp, str):
        try:
            data["dispatch_payload"] = json.loads(dp)
        except Exception:
            logger.warning(
                "get_entry_status: dispatch_payload is non-parseable string for entry %s",
                entry_id,
            )
    return data


async def save_extraction_edit(
    entry_id: str,
    user_id: str,
    stamp_kind: str,
    field_path: str,
    original_value: str | None,
    edited_value: str,
    edit_type: str,
    pipeline_version: str | None = None,
) -> dict:
    from fastapi import HTTPException

    entry_row = (
        supabase.table("entries")
        .select("id, user_id, dispatch_payload")
        .eq("id", entry_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if not entry_row.data:
        raise HTTPException(status_code=404, detail="Entry not found")

    row = entry_row.data[0]

    supabase.table("extraction_edits").insert(
        {
            "user_id": user_id,
            "entry_id": entry_id,
            "stamp_kind": stamp_kind,
            "field_path": field_path,
            "original_value": original_value,
            "edited_value": edited_value,
            "edit_type": edit_type,
            "pipeline_version": pipeline_version,
        }
    ).execute()

    # Patch dispatch_payload.stamps in-place
    dispatch = row.get("dispatch_payload") or {}
    stamps = dispatch.get("stamps", [])
    for stamp in stamps:
        if stamp.get("kind") == stamp_kind and stamp.get("value") == original_value:
            stamp["value"] = edited_value
            break
    dispatch["stamps"] = stamps

    supabase.table("entries").update({"dispatch_payload": dispatch}).eq("id", entry_id).execute()

    logger.info(
        "Extraction edit saved: entry=%s kind=%s '%s' -> '%s'",
        entry_id,
        stamp_kind,
        original_value,
        edited_value,
    )


async def get_dashboard_stats(user_id: str, user_timezone: str = "UTC") -> dict:
    """Real counts for the Today view header + stat cards.

    Returns:
        {
          "total_entries": int,        # all-time completed, non-deleted (VOL.)
          "entries_this_week": int,    # Monday 00:00 -> Sunday 23:59:59 in user tz
          "active_projects": int,      # projects with status='active'
          "completed_projects": int,   # projects with status='completed'
          "hidden_projects": int,      # projects with status='hidden' (the "+N")
          "entities_tracked": int,     # distinct entities with mention_count > 0
        }
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(user_timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)
    # Monday-start week in the user's local timezone, then convert to UTC for filtering.
    weekday = now_local.weekday()  # Monday = 0
    week_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=weekday)
    week_start_utc = week_start_local.astimezone(ZoneInfo("UTC"))

    total_resp = (
        supabase.table("entries")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .or_(_EXCLUDE_DUPLICATE_ORPHANS)
        .execute()
    )
    total_entries = total_resp.count or 0

    week_resp = (
        supabase.table("entries")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .or_(_EXCLUDE_DUPLICATE_ORPHANS)
        .gte("created_at", week_start_utc.isoformat())
        .execute()
    )
    entries_this_week = week_resp.count or 0

    active_resp = (
        supabase.table("projects")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    active_projects = active_resp.count or 0

    completed_resp = (
        supabase.table("projects")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .execute()
    )
    completed_projects = completed_resp.count or 0

    hidden_resp = (
        supabase.table("projects")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "hidden")
        .execute()
    )
    hidden_projects = hidden_resp.count or 0

    entities_resp = (
        supabase.table("entities")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gt("mention_count", 0)
        .execute()
    )
    entities_tracked = entities_resp.count or 0

    return {
        "total_entries": total_entries,
        "entries_this_week": entries_this_week,
        "active_projects": active_projects,
        "completed_projects": completed_projects,
        "hidden_projects": hidden_projects,
        "entities_tracked": entities_tracked,
    }


async def get_showed_up_stats(user_id: str, user_timezone: str = "UTC") -> dict:
    """Distinct-day journal-submission stats for the sidebar widget.

    Returns:
        {
          "count": int             # distinct local-calendar days journaled, all-time
          "daily_buckets": int[]   # entry counts for the last 14 days, oldest-first
        }
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(user_timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    rows = (
        supabase.table("entries")
        .select("created_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .execute()
    )
    entries = rows.data or []

    today_local = datetime.now(tz).date()
    bucket_dates = [today_local - timedelta(days=13 - i) for i in range(14)]
    bucket_index = {d: i for i, d in enumerate(bucket_dates)}
    buckets = [0] * 14
    distinct_days: set[str] = set()

    for row in entries:
        raw_ts = row.get("created_at")
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except Exception:
            continue
        local_date = ts.astimezone(tz).date()
        distinct_days.add(local_date.isoformat())
        if local_date in bucket_index:
            buckets[bucket_index[local_date]] += 1

    return {"count": len(distinct_days), "daily_buckets": buckets}
    return {"status": "saved"}
