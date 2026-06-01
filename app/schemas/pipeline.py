"""Pydantic schemas for pipeline-node structured outputs.

These are the response schemas handed to Gemini via
`with_structured_output(..., method="json_schema")`. Keep them separate from the
FastAPI request/response models in this package's __init__ — these describe LLM
output shape, not HTTP payloads.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.state import ClassifierType, EntityType, RelationType


class ClassifierResult(BaseModel):
    """Schema for the classify node output. Categories must be valid
    ClassifierType values; at least one required; at most four to prevent
    over-tagging."""
    categories: list[ClassifierType] = Field(
        default_factory=list,
        min_length=1,
        max_length=4,
    )


class TitleSummary(BaseModel):
    """Schema for the title_summary node output. A concise emoji title plus a
    short first-person summary."""
    auto_title: str = Field(min_length=1, max_length=80)
    summary: str = Field(default="", max_length=400)


class ExtractedEntity(BaseModel):
    """A single named entity extracted from a journal entry."""
    name: str = Field(min_length=1, max_length=120)
    type: EntityType


class EntityList(BaseModel):
    """Schema for the extract_entities node output. Gemini's json_schema mode
    doesn't reliably support top-level list output, so the list is wrapped in
    an object."""
    entities: list[ExtractedEntity] = Field(default_factory=list, max_length=50)


class ExtractedRelation(BaseModel):
    """A single semantic relation between two entities. Types and relation are
    enum-constrained; direction validity and entity-membership are enforced as
    Python post-processing in the node, not by this schema."""
    source: str
    source_type: EntityType
    target: str
    target_type: EntityType
    relation: RelationType


class RelationList(BaseModel):
    """Schema for the extract_relations node output. List wrapped in an object
    because Gemini's json_schema mode doesn't reliably emit a top-level list.
    Capped at 5 to match the node's max-relations rule."""
    relations: list[ExtractedRelation] = Field(default_factory=list, max_length=5)


class TimeRange(BaseModel):
    """Inclusive date range with an optional explicit time-of-day modifier."""
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time_of_day: Optional[Literal["morning", "afternoon", "evening", "night"]] = None


class EntityRef(BaseModel):
    """A known entity the question refers to, used for disambiguation."""
    name: str
    type: EntityType


class RoutingDecision(BaseModel):
    """Schema for the query_understanding_agent (Ask routing) output."""
    query_types: list[
        Literal["temporal", "semantic", "recent", "dashboard", "keyword"]
    ] = Field(min_length=1)
    time_range: Optional[TimeRange] = None
    entities_mentioned: list[EntityRef] = Field(default_factory=list)
    dashboard_context_needed: bool = False
