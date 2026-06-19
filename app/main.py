# app/main.py
import logging
import os
from typing import Optional

import sentry_sdk
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from langfuse import Langfuse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.auth import get_current_user
from app.dependencies.rate_limit import ask_rate_limit, entry_rate_limit
from app.services.analytics import track
from app.services.cost_cap import check_cost_cap
from app.services.tier_service import tier_service
from app.schemas import (
    DeadlineDateUpdateRequest,
    DeadlineStatusUpdateRequest,
    EntryRequest,
    EntryResponse,
    ExtractionEditRequest,
    MessagesResponse,
    ProjectStatusUpdateRequest,
    SendMessageRequest,
    TimezoneUpdateRequest,
)
from app.services import (
    ask_service,
    conversation,
    deadline_service,
    entity_service,
    entry_service,
    insight_service,
    project_service,
    tagline_service,
)
from app.payments.router import router as payments_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

load_dotenv()
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN_BACKEND"),
    integrations=[StarletteIntegration(), FastApiIntegration()],
    traces_sample_rate=0.2,
    profiles_sample_rate=0.1,
    environment="production",
    send_default_pii=False,
)
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

app.include_router(payments_router, prefix="/payments", tags=["payments"])


@app.get("/health")
async def health_check():
    # Railway injects RAILWAY_GIT_COMMIT_SHA on every deploy. Surface it here so
    # we can curl /health and instantly verify which commit is live.
    commit = os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown")
    return {
        "status": "alive",
        "commit": commit[:8] if commit != "unknown" else "unknown",
        "service": "mindgraph-backend",
    }


@app.post("/entries", response_model=EntryResponse)
async def create_entry(entry: EntryRequest, user_id: str = Depends(get_current_user)):
    return await entry_service.create_entry(entry, user_id)


@app.get("/entries")
async def get_entries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    mood: Optional[str] = Query(default=None),
    person: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user),
):
    return await entry_service.list_entries(
        user_id,
        page=page,
        page_size=page_size,
        mood=mood,
        person=person,
        category=category,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )


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
    browser_timezone: Optional[str] = Query(default=None),
    user_id: str = Depends(get_current_user),
    _rl: None = Depends(ask_rate_limit),
):
    tier = await tier_service.get_user_tier(user_id)
    await check_cost_cap(user_id, tier)
    answer = await ask_service.ask(question, user_id, browser_timezone=browser_timezone)
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


def _meter_conversation_routes() -> bool:
    """Kill switch for the conversation-route guards (STATE Critical #2 fix).

    Default ON. Set METER_CONVERSATION_ROUTES=0 to disable in seconds via a
    Railway env change (no redeploy/revert) if metering misfires on this live
    path — the route then behaves exactly as it did before metering was added.
    """
    return os.getenv("METER_CONVERSATION_ROUTES", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


@app.post("/conversations/messages", response_model=MessagesResponse)
async def send_conversation_message(
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    user_id: str = Depends(get_current_user),
):
    # Dependencies can't branch on request-body mode, so meter inside the
    # handler. http_request is the real Starlette Request (FastAPI injects it
    # by type), which the IP guard inside ask_rate_limit/entry_rate_limit needs.
    metering_on = _meter_conversation_routes()
    tier = await tier_service.get_user_tier(user_id) if metering_on else None

    if request.mode == "ask":
        if metering_on:
            await ask_rate_limit(http_request, user_id)
            await check_cost_cap(user_id, tier)
        return await conversation.send_ask_message(
            user_id, request.content, browser_timezone=request.browser_timezone,
        )

    if metering_on:
        await entry_rate_limit(http_request, user_id)
        await check_cost_cap(user_id, tier)
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


@app.post("/deadlines/{deadline_id}/restore")
async def restore_deadline(
    deadline_id: str,
    user_id: str = Depends(get_current_user),
):
    return await deadline_service.restore_deadline(deadline_id, user_id)


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
    track(user_id, "entry_submitted", {"tier": tier})
    return await entry_service.create_entry_async(entry, background_tasks, user_id)


# Must be declared before /entries/{entry_id} routes -- FastAPI matches in declaration order.
@app.get("/entries/filter-options")
async def get_filter_options(user_id: str = Depends(get_current_user)):
    return await entry_service.get_filter_options(user_id)


@app.get("/entries/{entry_id}/status")
async def get_entry_status(entry_id: str, user_id: str = Depends(get_current_user)):
    return await entry_service.get_entry_status(entry_id, user_id)


@app.delete("/entries/{entry_id}")
async def delete_entry(entry_id: str, user_id: str = Depends(get_current_user)):
    return await entry_service.soft_delete_entry(entry_id, user_id)


@app.post("/entries/{entry_id}/edits")
async def save_entry_edit(
    entry_id: str,
    edit: ExtractionEditRequest,
    user_id: str = Depends(get_current_user),
):
    return await entry_service.save_extraction_edit(
        entry_id=entry_id,
        user_id=user_id,
        stamp_kind=edit.stamp_kind,
        field_path=edit.field_path,
        original_value=edit.original_value,
        edited_value=edit.edited_value,
        edit_type=edit.edit_type,
    )


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


@app.get("/insights/tagline")
async def insights_tagline(
    user_tz: Optional[str] = Query(default="UTC"),
    user_id: str = Depends(get_current_user),
):
    return await tagline_service.get_or_generate_tagline(user_id, user_tz or "UTC")


@app.get("/stats/showed-up")
async def get_showed_up_stats(
    user_tz: Optional[str] = Query(default="UTC"),
    user_id: str = Depends(get_current_user),
):
    return await entry_service.get_showed_up_stats(user_id, user_tz or "UTC")


@app.get("/stats/dashboard")
async def get_dashboard_stats(
    user_tz: Optional[str] = Query(default="UTC"),
    user_id: str = Depends(get_current_user),
):
    return await entry_service.get_dashboard_stats(user_id, user_tz or "UTC")


@app.get("/users/me/timezone")
async def get_user_timezone(user_id: str = Depends(get_current_user)):
    from app.db import get_user_timezone as _get_tz
    tz = await _get_tz(user_id)
    return {"timezone": tz}


@app.patch("/users/me/timezone")
async def update_user_timezone(
    body: TimezoneUpdateRequest,
    user_id: str = Depends(get_current_user),
):
    from app.db import is_valid_iana_tz, set_user_timezone
    if not is_valid_iana_tz(body.timezone):
        raise HTTPException(status_code=422, detail=f"Invalid IANA timezone: {body.timezone}")
    await set_user_timezone(user_id, body.timezone)
    return {"timezone": body.timezone}
