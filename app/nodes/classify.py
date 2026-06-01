from app.llm import flash as model
from app.state import ClassifierType, JournalState
from app.schemas.pipeline import ClassifierResult
from typing import get_args

CLASSIFIER_TYPES = get_args(ClassifierType)

allowed_types_str = ", ".join(CLASSIFIER_TYPES)

# Structured output: Gemini enforces the ClassifierResult shape (enum-constrained
# list, 1-4 items) via response_json_schema, so the node no longer hand-parses
# JSON. method="json_schema" is explicit — don't rely on the default.
structured_model = model.with_structured_output(ClassifierResult, method="json_schema")


def build_classifier_prompt(text: str) -> str:
    return f"""
You are a classifier engine.

Classify the journal entry into the following categories:

{allowed_types_str}

Journal Entry:
{text}

Extract all suitable classifiers from the journal entry. Use only the allowed
types. If nothing suits, select only "other".
"""


async def classify(state: JournalState) -> dict:

    text = state['cleaned_text']

    prompt = build_classifier_prompt(text)

    result = await structured_model.ainvoke(prompt)

    return {"classifier": result.categories}
