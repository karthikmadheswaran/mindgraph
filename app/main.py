# app/main.py
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from langfuse import Langfuse

from app.auth import get_current_user
from app.schemas import (
    DeadlineDateUpdateRequest,
    DeadlineStatusUpdateRequest,
    EntryRequest,
    EntryResponse,
    ProjectStatusUpdateRequest,
)
from app.services import (
    ask_service,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://mindgraph-frontend-production.up.railway.app",
    ],
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


@app.post("/ask")
async def ask_question(
    question: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    answer = await ask_service.ask(question, user_id)
    background_tasks.add_task(ask_service.compact_old_messages, user_id)
    return {"answer": answer}


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
    user_id: str = Depends(get_current_user),
):
    return await entry_service.create_entry_async(entry, background_tasks, user_id)


@app.get("/entries/{entry_id}/status")
async def get_entry_status(entry_id: str, user_id: str = Depends(get_current_user)):
    return await entry_service.get_entry_status(entry_id, user_id)


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
