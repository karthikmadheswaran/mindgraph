from typing import Literal

from pydantic import BaseModel


class EntryRequest(BaseModel):
    raw_text: str
    input_type: str = "text"
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
