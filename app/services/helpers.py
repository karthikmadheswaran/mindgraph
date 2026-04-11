import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

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
