# app/main.py
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Literal, Optional
from datetime import datetime, timezone
from app.graph import build_graph
from app.nodes.store import supabase
from app.embeddings import get_embedding
from app.retrieval import advanced_search
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from app.auth import get_current_user
from app.insights_engine import (
    generate_weekly_digest,
    generate_patterns,
    generate_forgotten_projects,
    clear_old_insights,
    regenerate_insights_background  
)
load_dotenv()
Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import re
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.1)

app = FastAPI(title="Mindgraph Journal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://mindgraph-frontend-production.up.railway.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

workflow=build_graph()

class EntryRequest(BaseModel):
    raw_text: str
    input_type: str="text"
    user_timezone: str = "UTC"

class EntryResponse(BaseModel):
    auto_title: str
    summary: str
    classifier: list
    core_entities: list
    deadline: list


class DeadlineStatusUpdateRequest(BaseModel):
    status: Literal["pending", "done", "missed", "snoozed"]


class DeadlineDateUpdateRequest(BaseModel):
    due_date: str


class ProjectStatusUpdateRequest(BaseModel):
    status: Literal["active", "hidden", "completed"]


VALID_DEADLINE_STATUSES = {"pending", "done", "missed", "snoozed"}
VALID_PROJECT_STATUSES = {"active", "hidden", "completed"}
DEADLINE_DUE_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?$"
)


def parse_status_filter(
    status_param: Optional[str],
    default_statuses: list[str],
    valid_statuses: set[str],
    error_detail: str,
) -> list[str]:
    if status_param is None:
        return list(default_statuses)

    statuses = [value.strip() for value in status_param.split(",")]
    if not statuses or any(not value for value in statuses):
        raise HTTPException(status_code=422, detail=error_detail)

    invalid_statuses = [value for value in statuses if value not in valid_statuses]
    if invalid_statuses:
        raise HTTPException(status_code=422, detail=error_detail)

    deduped_statuses = []
    for value in statuses:
        if value not in deduped_statuses:
            deduped_statuses.append(value)

    return deduped_statuses


def parse_deadline_status_filter(status_param: Optional[str]) -> list[str]:
    return parse_status_filter(
        status_param,
        ["pending"],
        VALID_DEADLINE_STATUSES,
        "Invalid deadline status filter",
    )


def parse_project_status_filter(status_param: Optional[str]) -> list[str]:
    return parse_status_filter(
        status_param,
        ["active"],
        VALID_PROJECT_STATUSES,
        "Invalid project status filter",
    )


def parse_due_date_value(due_date: str) -> datetime:
    value = str(due_date or "").strip()
    if not DEADLINE_DUE_DATE_PATTERN.fullmatch(value):
        raise HTTPException(status_code=422, detail="Invalid due_date format")

    for datetime_format in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, datetime_format)
        except ValueError:
            continue

    raise HTTPException(status_code=422, detail="Invalid due_date format")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_suppressed_project_entity_ids(user_id: str) -> set[str]:
    result = (
        supabase.table("suppressed_project_entities")
        .select("entity_id")
        .eq("user_id", user_id)
        .execute()
    )

    return {
        row["entity_id"]
        for row in (result.data or [])
        if row.get("entity_id")
    }


def mark_overdue_deadlines_as_missed(user_id: str) -> None:
    now_iso = utc_now_iso()
    (
        supabase.table("deadlines")
        .update(
            {
                "status": "missed",
                "status_changed_at": now_iso,
            }
        )
        .eq("user_id", user_id)
        .eq("status", "pending")
        .lt("due_date", now_iso)
        .execute()
    )


def clear_deadline_project_links(project_id: str) -> None:
    try:
        (
            supabase.table("deadlines")
            .update({"project_id": None})
            .eq("project_id", project_id)
            .execute()
        )
    except Exception as exc:
        message = str(exc).lower()
        if "project_id" in message and (
            "column" in message or "schema cache" in message
        ):
            return
        raise

@app.get("/health")
async def health_check():
    return {"status": "alive"}

@app.post("/entries", response_model=EntryResponse)
async def create_entry(entry: EntryRequest, user_id: str = Depends(get_current_user)):
    langfuse_handler = LangfuseCallbackHandler()
    state={
        "raw_text": entry.raw_text,
        "user_id": user_id,
        "user_timezone": entry.user_timezone,
        "input_type": entry.input_type,
        "cleaned_text": "",
        "auto_title": "",
        "summary": "",
        "classifier": [],
        "core_entities": [],
        "deadline": [],
        "relations": [],
        "trigger_check": False,
        "duplicate_of": None,
        "dedup_check_result": None
    }

    result = await workflow.ainvoke(state, config={"callbacks": [langfuse_handler]})


    return EntryResponse(
        auto_title=result["auto_title"],
        summary=result["summary"],
        classifier=result["classifier"],
        core_entities=result["core_entities"],
        deadline=result["deadline"]
    )

@app.get("/entries")
async def get_entries(user_id: str = Depends(get_current_user)):
    result = supabase.table("entries")\
        .select("id, raw_text, cleaned_text, auto_title, summary, created_at, status, pipeline_stage") \
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .limit(20) \
        .execute()
    
    return {"entries": result.data}

@app.get("/search")
async def search_entries(query: str, user_id: str = Depends(get_current_user)):
    # Step 1: Convert the search query into an embedding
    query_embedding = await get_embedding(query)
    
    # Step 2: Search Supabase for similar entries
    result = supabase.rpc("match_entries", {
        "query_embedding": query_embedding,
        "match_count": 5,
        "filter_user_id": user_id
    }).execute()
    
    return {"results": result.data}

def extract_text_from_response(response):
    content = response.content

    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()

@app.post("/ask")
async def ask_question(question: str, user_id: str = Depends(get_current_user)):
    langfuse_handler = LangfuseCallbackHandler()
    
    query_embedding = await get_embedding(question)
    result = supabase.rpc("match_entries", {
        "query_embedding": query_embedding,
        "match_count": 5,
        "filter_user_id": user_id
    }).execute()
    
    if not result.data:
        return {"answer": "No relevant entries found."}
    
    formatted_entries = []
    for i, entry in enumerate(result.data, 1):
        date = entry.get("created_at", "Unknown date")
        title = entry.get("auto_title", "No title")
        formatted_entries.append(f"Entry {i} (created at {date}, title: {title}):\n{entry['cleaned_text']}")
    
    context_text = "\n\n---\n\n".join(formatted_entries)

    prompt = f"""You are an assistant for a personal journal app. A user has asked the following question:
    "{question}"

    You have access to the following relevant journal entries:
    {context_text}
    
    Based on these journal entries, provide a helpful answer to the user's question. 
    If the journal entries do not contain relevant information, say "I don't know".
    """
    
    response = await model.ainvoke(prompt, config={"callbacks": [langfuse_handler]})
    answer = extract_text_from_response(response)
    return {"answer": answer}

@app.get("/deadlines")
async def get_deadlines(
    status: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user),
):
    mark_overdue_deadlines_as_missed(user_id)
    status_filters = parse_deadline_status_filter(status)
    result = (
        supabase.table("deadlines")
        .select("id, description, due_date, status, status_changed_at")
        .eq("user_id", user_id)
        .in_("status", status_filters)
        .order("due_date", desc=False)
        .execute()
    )
    
    return {"deadlines": result.data}


@app.patch("/deadlines/{deadline_id}/status")
async def update_deadline_status(
    deadline_id: str,
    update: DeadlineStatusUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id, description, due_date, status, status_changed_at")
        .eq("id", deadline_id)
        .limit(1)
        .execute()
    )

    if not deadline_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    deadline = deadline_result.data[0]
    if deadline.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated_result = (
        supabase.table("deadlines")
        .update(
            {
                "status": update.status,
                "status_changed_at": utc_now_iso(),
            },
            returning="representation",
        )
        .eq("id", deadline_id)
        .execute()
    )

    if not updated_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    return updated_result.data[0]


@app.patch("/deadlines/{deadline_id}/date")
async def update_deadline_date(
    deadline_id: str,
    update: DeadlineDateUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    parsed_due_date = parse_due_date_value(update.due_date)

    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id, description, due_date, status, status_changed_at")
        .eq("id", deadline_id)
        .limit(1)
        .execute()
    )

    if not deadline_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    deadline = deadline_result.data[0]
    if deadline.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated_result = (
        supabase.table("deadlines")
        .update({"due_date": parsed_due_date.isoformat()}, returning="representation")
        .eq("id", deadline_id)
        .execute()
    )

    if not updated_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    return updated_result.data[0]


@app.delete("/deadlines/{deadline_id}")
async def delete_deadline(
    deadline_id: str,
    user_id: str = Depends(get_current_user),
):
    deadline_result = (
        supabase.table("deadlines")
        .select("id, user_id")
        .eq("id", deadline_id)
        .limit(1)
        .execute()
    )

    if not deadline_result.data:
        raise HTTPException(status_code=404, detail="Deadline not found")

    deadline = deadline_result.data[0]
    if deadline.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    supabase.table("deadlines").delete().eq("id", deadline_id).execute()
    return {"success": True, "id": deadline_id}


@app.get("/projects")
async def get_projects(
    status: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user),
):
    status_filters = parse_project_status_filter(status)
    result = (
        supabase.table("projects")
        .select(
            "id, name, status, first_mentioned_at, last_mentioned_at, "
            "mention_count, running_summary, status_changed_at"
        )
        .eq("user_id", user_id)
        .in_("status", status_filters)
        .order("mention_count", desc=True)
        .execute()
    )

    return {"projects": result.data}


@app.patch("/projects/{project_id}/status")
async def update_project_status(
    project_id: str,
    update: ProjectStatusUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    project_result = (
        supabase.table("projects")
        .select(
            "id, user_id, name, status, first_mentioned_at, "
            "last_mentioned_at, mention_count, running_summary, "
            "status_changed_at, source_entity_id"
        )
        .eq("id", project_id)
        .limit(1)
        .execute()
    )

    if not project_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_result.data[0]
    if project.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    updated_result = (
        supabase.table("projects")
        .update(
            {
                "status": update.status,
                "status_changed_at": utc_now_iso(),
            },
            returning="representation",
        )
        .eq("id", project_id)
        .execute()
    )

    if not updated_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    return updated_result.data[0]


@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
):
    project_result = (
        supabase.table("projects")
        .select("id, user_id, source_entity_id")
        .eq("id", project_id)
        .limit(1)
        .execute()
    )

    if not project_result.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_result.data[0]
    if project.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    source_entity_id = project.get("source_entity_id")
    if source_entity_id:
        (
            supabase.table("suppressed_project_entities")
            .upsert(
                {"user_id": user_id, "entity_id": source_entity_id},
                on_conflict="user_id,entity_id",
            )
            .execute()
        )

    clear_deadline_project_links(project_id)
    supabase.table("projects").delete().eq("id", project_id).execute()
    return {"success": True, "id": project_id}


@app.get("/progress")
async def get_progress(user_id: str = Depends(get_current_user)):
    mark_overdue_deadlines_as_missed(user_id)

    deadline_result = (
        supabase.table("deadlines")
        .select("id, description, due_date, status, status_changed_at")
        .eq("user_id", user_id)
        .in_("status", ["done", "missed"])
        .order("status_changed_at", desc=True)
        .execute()
    )

    project_result = (
        supabase.table("projects")
        .select(
            "id, name, mention_count, first_mentioned_at, status, "
            "status_changed_at"
        )
        .eq("user_id", user_id)
        .eq("status", "completed")
        .order("status_changed_at", desc=True)
        .execute()
    )

    return {
        "deadlines": deadline_result.data or [],
        "projects": project_result.data or [],
    }


@app.get("/entities")
async def get_entities(user_id: str = Depends(get_current_user)):
    suppressed_entity_ids = get_suppressed_project_entity_ids(user_id)
    result = (
        supabase.table("entities")
        .select("id, name, entity_type, mention_count")
        .eq("user_id", user_id)
        .order("mention_count", desc=True)
        .limit(60)
        .execute()
    )

    entities = [
        entity
        for entity in (result.data or [])
        if not (
            entity.get("entity_type") == "project"
            and entity.get("id") in suppressed_entity_ids
        )
    ][:20]

    return {"entities": entities}


@app.get("/entity-relations")
async def get_entity_relations(user_id: str = Depends(get_current_user)):
    suppressed_entity_ids = get_suppressed_project_entity_ids(user_id)
    relation_result = (
        supabase.table("entity_relations")
        .select(
            "source_entity_id, target_entity_id, relation_type, "
            "confidence, source_entry_id, updated_at"
        )
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(200)
        .execute()
    )

    relation_rows = [
        row
        for row in (relation_result.data or [])
        if row.get("source_entity_id") not in suppressed_entity_ids
        and row.get("target_entity_id") not in suppressed_entity_ids
    ]
    entity_ids = sorted(
        {
            row["source_entity_id"]
            for row in relation_rows
            if row.get("source_entity_id")
        }
        | {
            row["target_entity_id"]
            for row in relation_rows
            if row.get("target_entity_id")
        }
    )

    if not entity_ids:
        return {"relations": []}

    entity_result = (
        supabase.table("entities")
        .select("id, name, entity_type")
        .eq("user_id", user_id)
        .in_("id", entity_ids)
        .execute()
    )

    entity_lookup = {
        entity["id"]: entity
        for entity in (entity_result.data or [])
    }

    relations = []
    for row in relation_rows:
        source = entity_lookup.get(row.get("source_entity_id"))
        target = entity_lookup.get(row.get("target_entity_id"))

        if not source or not target:
            continue

        relations.append(
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "source_type": source["entity_type"],
                "target_id": target["id"],
                "target_name": target["name"],
                "target_type": target["entity_type"],
                "relation_type": row["relation_type"],
                "confidence": row.get("confidence", 1.0),
                "source_entry_id": row.get("source_entry_id"),
                "updated_at": row.get("updated_at"),
            }
        )

    return {"relations": relations}

@app.post("/entries/stream")
async def create_entry_stream(entry: EntryRequest, user_id: str = Depends(get_current_user)):
    langfuse_handler = LangfuseCallbackHandler()
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

    async def event_stream():
        final_result = {}
        try:
            async for event in workflow.astream(state, config={"callbacks": [langfuse_handler]}):
                node_name = list(event.keys())[0]
                node_output = event[node_name]
                if node_output and isinstance(node_output, dict):
                    final_result.update(node_output)
                update = {"node": node_name, "status": "completed"}
                yield f"data: {json.dumps(update)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'node': 'error', 'message': str(e)})}\n\n"

        # Convert deadlines to serializable format
        deadlines = final_result.get('deadline', [])
        serializable_deadlines = []
        for d in deadlines:
            serializable_deadlines.append({
                "description": d.get("description", ""),
                "due_at": str(d.get("due_at", "")),
                "raw_text": d.get("raw_text", ""),
            })

        yield f"data: {json.dumps({'node': 'done', 'result': {
            'auto_title': final_result.get('auto_title', ''),
            'summary': final_result.get('summary', ''),
            'classifier': final_result.get('classifier', []),
            'core_entities': final_result.get('core_entities', []),
            'deadline': serializable_deadlines,
        }})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/entries/async")
async def create_entry_async(entry: EntryRequest, background_tasks: BackgroundTasks, user_id: str = Depends(get_current_user)):
    # Insert skeleton row immediately so it appears on dashboard
    skeleton = supabase.table("entries").insert({
        "raw_text": entry.raw_text,
        "user_id": user_id,
        "cleaned_text": "",
        "auto_title": "",
        "summary": "",
        "status": "processing",
        "pipeline_stage": "normalize",
    }).execute()

    entry_id = skeleton.data[0]["id"] if skeleton.data else None

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
        "entry_id": str(entry_id) if entry_id else None,
    }

    async def process_entry():
        try:
            langfuse_handler = LangfuseCallbackHandler()
            async for event in workflow.astream(state, config={"callbacks": [langfuse_handler]}):
                node_name = list(event.keys())[0]
                if entry_id:
                    supabase.table("entries").update({
                        "pipeline_stage": node_name
                    }).eq("id", entry_id).execute()
            
            # Trigger C: regenerate insights after pipeline completes
            await regenerate_insights_background(user_id)
            
        except Exception as e:
            print(f"❌ Background processing error: {e}")
            if entry_id:
                supabase.table("entries").update({
                    "status": "error",
                    "pipeline_stage": None
                }).eq("id", entry_id).execute()

    background_tasks.add_task(process_entry)

    return {"status": "processing", "entry_id": entry_id, "message": "Your entry is being processed. Check the dashboard in a few seconds."}

@app.get("/entries/{entry_id}/status")
async def get_entry_status(entry_id: str, user_id: str = Depends(get_current_user)):
    result = supabase.table("entries") \
        .select("id, status, pipeline_stage") \
        .eq("id", entry_id) \
        .eq("user_id", user_id) \
        .single() \
        .execute()
    return result.data

@app.get("/search")
async def search_entries_endpoint(query: str, user_id: str = Depends(get_current_user)):
    results = await advanced_search(query, user_id, match_count=5)
    return {"results": results}
    

@app.get("/insights")
async def get_insights(user_id: str = Depends(get_current_user)):
    """Read cached insights from database — no LLM call"""
    result = supabase.table("insights") \
        .select("id, insight_type, content, severity, created_at") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .limit(10) \
        .execute()
    return {"insights": result.data or []}

@app.get("/insights/weekly")
async def insights_weekly(user_id: str = Depends(get_current_user)):
    """Read cached weekly digest — no LLM call"""
    result = supabase.table("insights") \
        .select("content, created_at") \
        .eq("user_id", user_id) \
        .eq("insight_type", "weekly_digest") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    if result.data:
        import json
        return {"status": "ok", "data": json.loads(result.data[0]["content"])}
    return {"status": "ok", "data": None}

@app.get("/insights/patterns")
async def insights_patterns(user_id: str = Depends(get_current_user)):
    """Read cached patterns — no LLM call"""
    result = supabase.table("insights") \
        .select("content, created_at") \
        .eq("user_id", user_id) \
        .eq("insight_type", "pattern") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    if result.data:
        import json
        return {"status": "ok", "data": json.loads(result.data[0]["content"])}
    return {"status": "ok", "data": None}

@app.get("/insights/forgotten")
async def insights_forgotten(user_id: str = Depends(get_current_user)):
    """Read cached forgotten projects — no LLM call"""
    result = supabase.table("insights") \
        .select("content, created_at") \
        .eq("user_id", user_id) \
        .eq("insight_type", "forgotten_projects") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    if result.data:
        import json
        return {"status": "ok", "data": json.loads(result.data[0]["content"])}
    return {"status": "ok", "data": None}






    
