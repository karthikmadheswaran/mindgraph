from app.llm import extract_text, flash as model
from app.state import ClassifierType, JournalState
from typing import get_args
import json

CLASSIFIER_TYPES = get_args(ClassifierType)

allowed_types_str = ", ".join(CLASSIFIER_TYPES)

def build_classifier_prompt(text: str) -> str:
    return f"""
You are a classifier engine.

Classify the journal entry into one of the following categories:

{allowed_types_str}

Journal Entry:
{text}

Extract all suitable classifiers from the journal entry, if nothing suits, only select "other".

Return list of strings only. No explanation.

Format:
[
    "category_name", ...
]

Rules:
- Use only allowed types.
- If no classifiers exist, return ["other"].
- Do not include extra fields.

"""

def parse_classifiers(raw: str) -> list[str]:
    try:
        content = raw.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        data = json.loads(content)
    except json.JSONDecodeError:
        return ["other"]

    if not isinstance(data, list):
        return []

    valid = []

    for item in data:
        if isinstance(item, str):
            value=item.strip().lower()
            if value in CLASSIFIER_TYPES:
                valid.append(value)
            
    if not valid:
        valid.append("other")

    return valid


async def classify(state: JournalState) -> dict:

    text = state['cleaned_text']

    prompt = build_classifier_prompt(text)

    response = await model.ainvoke(prompt)

    content = extract_text(response)

    classifiers = parse_classifiers(content)

    return {"classifier": classifiers}



