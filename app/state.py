from typing import TypedDict, List, Literal, Optional, Annotated
from datetime import datetime
from langgraph.graph import add_messages

EntityType = Literal[
    "person",
    "project",
    "tool",
    "place",
    "organization",
    "event",
    "task",
    "none"
]

ClassifierType = Literal[
    "work",
    "personal",
    "health",
    "finance",
    "family",
    "hobby",
    "travel",
    "education",
    "other"
]

DedupCheckResult = Literal[
    "duplicate",
    "not_duplicate",
    "uncertain"
]

RelationType = Literal[
    "uses",
    "built_with",
    "works_on",
    "works_with",
    "located_at",
    "belongs_to",
    "part_of",
]

def keep_latest(existing, new):
    if new is None or new == [] or new == "" or new == False:
        return existing
    return new

class CoreEntityNode(TypedDict):
    name: str
    type: EntityType

class DeadlineNode(TypedDict):
    description: str
    due_at: datetime
    raw_text: str


class RelationEdge(TypedDict):
    source: str
    source_type: EntityType
    target: str
    target_type: EntityType
    relation: RelationType

class JournalState(TypedDict):
    user_id: str
    raw_text: str
    cleaned_text: Annotated[str, keep_latest]
    auto_title: Annotated[str, keep_latest]
    summary: Annotated[str, keep_latest]
    input_type: str
    attachment_url: str
    classifier: Annotated[list, keep_latest]
    core_entities: Annotated[list, keep_latest]
    deadline: Annotated[list, keep_latest]
    trigger_check: Annotated[bool, keep_latest]
    duplicate_of: Annotated[Optional[str], keep_latest]
    dedup_check_result: Annotated[Optional[str], keep_latest]
    entry_id: Annotated[Optional[str], keep_latest]
    relations: Annotated[list, keep_latest]



    


