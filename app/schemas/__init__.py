import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EntryRequest(BaseModel):
    raw_text: str
    input_type: str = "text"
    user_timezone: str = "UTC"


# Pragmatic email shape check — no email_validator dependency. Rejects the
# obvious garbage; the real gate is manual review before an email is copied
# into allowed_emails.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccessRequestBody(BaseModel):
    email: str
    note: Optional[str] = Field(default=None, max_length=280)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v) or len(v) > 254:
            raise ValueError("invalid email")
        return v


class SignupBody(BaseModel):
    email: str
    # min_length matches the frontend input and GoTrue's default policy.
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v) or len(v) > 254:
            raise ValueError("invalid email")
        return v


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


class SendMessageRequest(BaseModel):
    content: str
    mode: Literal["ask", "journal"]
    browser_timezone: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    user_id: str
    role: str
    content: str
    created_at: str
    metadata: dict = Field(default_factory=dict)
    entry_id: Optional[str] = None


class MessagesResponse(BaseModel):
    messages: list[MessageResponse]
    has_more: bool = False


class ExtractionEditRequest(BaseModel):
    stamp_kind: str
    field_path: str
    original_value: Optional[str] = None
    edited_value: str
    edit_type: Literal["correction", "deletion", "addition"]


class TimezoneUpdateRequest(BaseModel):
    timezone: str


class EntriesQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)
    mood: Optional[str] = None
    person: Optional[str] = None
    category: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    search: Optional[str] = None
