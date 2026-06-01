# app/db.py
import logging
import os
from zoneinfo import available_timezones

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger(__name__)

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY"),
)

_VALID_TIMEZONES: frozenset[str] = frozenset(available_timezones())


def is_valid_iana_tz(tz: str) -> bool:
    return tz in _VALID_TIMEZONES


async def get_user_timezone(user_id: str) -> str:
    result = (
        supabase.table("users")
        .select("timezone")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0].get("timezone") or "UTC"
    return "UTC"


async def set_user_timezone(user_id: str, tz: str) -> None:
    if not is_valid_iana_tz(tz):
        logger.warning("Rejecting invalid timezone %r for user %s", tz, user_id)
        return
    supabase.table("users").update({"timezone": tz}).eq("id", user_id).execute()


async def maybe_update_user_timezone(user_id: str, request_tz: str | None) -> None:
    """Auto-populate timezone on first entry submission only."""
    if not request_tz or request_tz == "UTC":
        return
    if not is_valid_iana_tz(request_tz):
        return
    current = await get_user_timezone(user_id)
    if current == "UTC":
        await set_user_timezone(user_id, request_tz)
