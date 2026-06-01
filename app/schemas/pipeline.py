"""Pydantic schemas for pipeline-node structured outputs.

These are the response schemas handed to Gemini via
`with_structured_output(..., method="json_schema")`. Keep them separate from the
FastAPI request/response models in this package's __init__ — these describe LLM
output shape, not HTTP payloads.
"""
from pydantic import BaseModel, Field

from app.state import ClassifierType, EntityType


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
