# app/main.py
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from langfuse import Langfuse

from app.auth import get_current_user
from app.dependencies.rate_limit import ask_rate_limit, entry_rate_limit
from app.services.cost_cap import check_cost_cap
from app.services.tier_service import tier_service
from app.schemas import (
    DeadlineDateUpdateRequest,
    DeadlineStatusUpdateRequest,
    EntryRequest,
    EntryResponse,
    MessagesResponse,
    ProjectStatusUpdateRequest,
    SendMessageRequest,
)
from app.services import (
    ask_service,
    conversation,
    deadline_service,
    entity_service,
    entry_service,
    insight_service,
    project_service,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

load_dotenv()
Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com"),
)

app = FastAPI(title="Mindgraph Journal API")

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "https://mindgraph-frontend-production.up.railway.app",
    "https://rawtxt.in",
    "https://www.rawtxt.in",
]


def get_cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS") or os.getenv("FRONTEND_ORIGINS")

    if not configured_origins:
        return DEFAULT_CORS_ORIGINS

    origins = [
        origin.strip().rstrip("/")
        for origin in configured_origins.split(",")
        if origin.strip()
    ]

    return origins or DEFAULT_CORS_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "alive"}


@app.post("/entries", response_model=EntryResponse)
async def create_entry(entry: EntryRequest, user_id: str = Depends(get_current_user)):
    return await entry_service.create_entry(entry, user_id)


@app.get("/entries")
async def get_entries(user_id: str = Depends(get_current_user)):
    return await entry_service.list_entries(user_id)


@app.get("/search")
async def search_entries(query: str, user_id: str = Depends(get_current_user)):
    return await entry_service.search_entries(query, user_id)


@app.get("/ask/history")
async def get_ask_history(user_id: str = Depends(get_current_user)):
    return await ask_service.get_history(user_id)


@app.get("/ask/memory")
async def get_user_memory(user_id: str = Depends(get_current_user)):
    return await ask_service.get_memory(user_id)


@app.post("/ask/new-session")
async def new_ask_session(user_id: str = Depends(get_current_user)):
    return await ask_service.new_session(user_id)


@app.post("/ask")
async def ask_question(
    question: str,
    background_tasks: BackgroundTasks,
    request: Request,
    user_id: str = Depends(get_current_user),
    _rl: None = Depends(ask_rate_limit),
):
    tier = await tier_service.get_user_tier(user_id)
    await check_cost_cap(user_id, tier)
    answer = await ask_service.ask(question, user_id)
    background_tasks.add_task(ask_service.compact_old_messages, user_id)
    return {"answer": answer}


@app.get("/conversations/messages", response_model=MessagesResponse)
async def get_conversation_messages(
    limit: int = Query(default=20, ge=1, le=50),
    before: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user),
):
    messages = await conversation.get_messages(user_id, limit=limit, before=before)
    return {"messages": messages, "has_more": len(messages) == limit}


@app.post("/conversations/messages", response_model=MessagesResponse)
async def send_conversation_message(
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    if request.mode == "ask":
        return await conversation.send_ask_message(user_id, request.content)
    return await conversation.send_journal_message(
        user_id,
        request.content,
        background_tasks,
    )


@app.get("/conversations/messages/{message_id}/status")
async def get_conversation_message_status(
    message_id: str,
    user_id: str = Depends(get_current_user),
):
    return await conversation.get_message_status(message_id, user_id)


@app.get("/deadlines")
async def get_deadlines(
    status: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user),
):
    return await deadline_service.list_deadlines(status, user_id)


@app.patch("/deadlines/{deadline_id}/status")
async def update_deadline_status(
    deadline_id: str,
    update: DeadlineStatusUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    return await deadline_service.update_deadline_status(
        deadline_id,
        update.status,
        user_id,
    )


@app.patch("/deadlines/{deadline_id}/date")
async def update_deadline_date(
    deadline_id: str,
    update: DeadlineDateUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    return await deadline_service.update_deadline_date(
        deadline_id,
        update.due_date,
        user_id,
    )


@app.delete("/deadlines/{deadline_id}")
async def delete_deadline(
    deadline_id: str,
    user_id: str = Depends(get_current_user),
):
    return await deadline_service.delete_deadline(deadline_id, user_id)


@app.get("/projects")
async def get_projects(
    status: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user),
):
    return await project_service.list_projects(status, user_id)


@app.patch("/projects/{project_id}/status")
async def update_project_status(
    project_id: str,
    update: ProjectStatusUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    return await project_service.update_project_status(
        project_id,
        update.status,
        user_id,
    )


@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user),
):
    return await project_service.delete_project(project_id, user_id)


@app.get("/progress")
async def get_progress(user_id: str = Depends(get_current_user)):
    return await project_service.get_progress(user_id)


@app.get("/entities")
async def get_entities(user_id: str = Depends(get_current_user)):
    return await entity_service.get_entities(user_id)


@app.get("/entity-relations")
async def get_entity_relations(user_id: str = Depends(get_current_user)):
    return await entity_service.get_entity_relations(user_id)


@app.post("/entries/stream")
async def create_entry_stream(entry: EntryRequest, user_id: str = Depends(get_current_user)):
    return await entry_service.create_entry_stream(entry, user_id)


@app.post("/entries/async")
async def create_entry_async(
    entry: EntryRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    user_id: str = Depends(get_current_user),
    _rl: None = Depends(entry_rate_limit),
):
    tier = await tier_service.get_user_tier(user_id)
    await check_cost_cap(user_id, tier)
    return await entry_service.create_entry_async(entry, background_tasks, user_id)


@app.get("/entries/{entry_id}/status")
async def get_entry_status(entry_id: str, user_id: str = Depends(get_current_user)):
    return await entry_service.get_entry_status(entry_id, user_id)


@app.delete("/entries/{entry_id}")
async def delete_entry(entry_id: str, user_id: str = Depends(get_current_user)):
    return await entry_service.soft_delete_entry(entry_id, user_id)


@app.get("/search")
async def search_entries_endpoint(query: str, user_id: str = Depends(get_current_user)):
    return await entry_service.advanced_search_entries(query, user_id)


@app.get("/insights")
async def get_insights(user_id: str = Depends(get_current_user)):
    return await insight_service.get_insights(user_id)


@app.get("/insights/weekly")
async def insights_weekly(user_id: str = Depends(get_current_user)):
    return await insight_service.get_weekly(user_id)


@app.get("/insights/patterns")
async def insights_patterns(user_id: str = Depends(get_current_user)):
    return await insight_service.get_patterns(user_id)


@app.get("/insights/forgotten")
async def insights_forgotten(user_id: str = Depends(get_current_user)):
    return await insight_service.get_forgotten(user_id)
