from app.state import JournalState,CoreEntityNode,EntityType
from datetime import datetime
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import get_args, List
import json
load_dotenv()

os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.1)

ENTITY_TYPES = get_args(EntityType)

allowed_types_str = ", ".join(ENTITY_TYPES)

def build_entity_prompt(text: str) -> str:
    return f"""
You are an entity extraction engine.

Extract all core entities from the journal entry.

Allowed types:
{allowed_types_str}

Return STRICT JSON only. No explanation.

Format:
[
  {{"name": "entity_name", "type": "entity_type"}}
]

Rules:
- Use only allowed types.
- If no entities exist, return [].
- Do not include extra fields.

Journal Entry:
{text}
"""

def extract_text_from_response(response):
    content = response.content

    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )

    return content.strip()

def parse_entities(raw: str) -> list[CoreEntityNode]:
    # Strip markdown code fences
    content = raw.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    valid = []
    for item in data:
        if (
            isinstance(item, dict)
            and "name" in item
            and "type" in item
            and item["type"] in ENTITY_TYPES
        ):
            valid.append(item)

    return valid


async def extract_entities(state: JournalState) -> dict:
    #Use LLM to classify the journal entry into one of the core entity types

    text = state['cleaned_text']

    prompt = build_entity_prompt(text)

    response = await model.ainvoke(prompt)

    content = extract_text_from_response(response)

    entities = parse_entities(content)

    return {"core_entities": entities}



