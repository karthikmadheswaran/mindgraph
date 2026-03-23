from app.state import JournalState,CoreEntityNode,ClassifierType
from datetime import datetime
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import get_args, List
import json
load_dotenv()

os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.1)

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

def extract_text_from_response(response):
    content = response.content

    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )

    return content.strip()

def parse_classifiers(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
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

    content = extract_text_from_response(response)

    classifiers = parse_classifiers(content)

    return {"classifier": classifiers}



