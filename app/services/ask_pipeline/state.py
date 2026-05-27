from typing import Annotated, Literal, Optional, TypedDict

from app.state import keep_latest

# Canonical time_of_day labels accepted on TimeRange. Hours are user-local
# (or UTC when the user's timezone is unknown — see temporal_retrieval.py).
TimeOfDay = Literal["morning", "afternoon", "evening", "night"]


class TimeRange(TypedDict, total=False):
    """Shape of the optional `time_range` field on AskState.

    The query_understanding_agent emits this from the user's question. All
    fields optional — a routing decision may omit `time_range` entirely, OR
    supply a date range without a `time_of_day` modifier.
    """
    start: str           # ISO date YYYY-MM-DD (inclusive)
    end: str             # ISO date YYYY-MM-DD (inclusive — coerced to exclusive)
    time_of_day: Optional[TimeOfDay]  # explicit time-of-day modifier, if any


class AskState(TypedDict):
    question: str
    user_id: str
    conversation_history: str
    long_term_memory: str

    query_types: Annotated[list, keep_latest]
    time_range: Annotated[Optional[dict], keep_latest]
    entities_mentioned: Annotated[list, keep_latest]
    dashboard_context_needed: Annotated[bool, keep_latest]
    today_str: Annotated[str, keep_latest]

    temporal_entries: Annotated[list, keep_latest]
    recent_summaries: Annotated[list, keep_latest]
    rag_entries: Annotated[list, keep_latest]
    dashboard_context: Annotated[dict, keep_latest]

    rag_max_similarity: Annotated[float, keep_latest]
    temporal_has_results: Annotated[bool, keep_latest]
    dashboard_has_results: Annotated[bool, keep_latest]
    is_low_confidence: Annotated[bool, keep_latest]

    assembled_context: Annotated[str, keep_latest]
    answer: Annotated[str, keep_latest]
