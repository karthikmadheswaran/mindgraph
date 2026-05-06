from typing import Annotated, Optional, TypedDict

from app.state import keep_latest


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

    assembled_context: Annotated[str, keep_latest]
    answer: Annotated[str, keep_latest]
