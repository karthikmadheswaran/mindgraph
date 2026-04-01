from app.state import JournalState, DeadlineNode
from datetime import datetime
import re
import os
import json

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.1)

USE_SEMANTIC_VALIDATOR = False


def build_deadline_prompt(text: str, raw_text: str) -> str:
    reference_date = datetime.now().strftime("%Y-%m-%d")
    return f"""
You are a strict deadline extraction engine.

Extract only concrete deadlines or scheduled commitments.

Reference Date:
{reference_date}

Cleaned Input:
{text}

Raw Input:
{raw_text}

Rules:
- Extract only if there is a clear time reference.
- The time reference must be tied to a real task, obligation, meeting, payment, submission, appointment, or event.
- Do not extract hopes, vague future thoughts, reflections, metadata dates, or project/status phrases.
- Do not invent deadlines that are not in the text.
- If a date is ambiguous and cannot be resolved confidently, skip it.

Do NOT extract examples like:
- new possibilities
- hope for a better day
- entry date
- project progress

Output Rules:
- Return STRICT JSON only.
- No markdown, no code fences, no explanation.
- Return a JSON array.
- If no deadlines exist, return [].
- Use exactly these keys for each item: "description", "due_at", "raw_text"
- "description" = short description of what the deadline is for
- "due_at" = date in YYYY-MM-DD format
- "raw_text" = the exact deadline phrase from the journal text
- Resolve relative dates using the Reference Date.
- Do not include extra fields.

Format:
[
  {{"description": "submit visa documents", "due_at": "YYYY-MM-DD", "raw_text": "by Friday"}}
]
""".strip()


def extract_text_from_response(response):
    content = response.content

    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )

    return content.strip()


def is_valid_deadline_candidate(
    description: str,
    raw_text: str,
    raw_source_text: str,
    cleaned_source_text: str,
) -> bool:
    description_l = description.lower().strip()
    raw_text_l = raw_text.lower().strip()
    raw_source_l = raw_source_text.lower()
    cleaned_source_l = cleaned_source_text.lower()

    if not description_l or not raw_text_l:
        return False

    bad_phrases = [
        "new possibilities",
        "hope for a better day",
        "entry date",
        "project progress",
    ]

    for phrase in bad_phrases:
        if phrase in description_l or phrase in raw_text_l:
            return False

    # raw_text can appear either in original user text or normalized cleaned text
    if raw_text_l not in raw_source_l and raw_text_l not in cleaned_source_l:
        return False

    return True


def parse_deadlines(
    raw: str,
    raw_source_text: str,
    cleaned_source_text: str,
) -> list[DeadlineNode]:
    raw = raw.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    valid: list[DeadlineNode] = []

    for item in data:
        if not isinstance(item, dict):
            continue

        description = item.get("description")
        due_at = item.get("due_at")
        extracted_raw_text = item.get("raw_text")

        if not all(isinstance(x, str) for x in [description, due_at, extracted_raw_text]):
            continue

        description = description.strip()
        due_at = due_at.strip()
        extracted_raw_text = extracted_raw_text.strip()

        if not description:
            continue

        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_at):
            continue

        if USE_SEMANTIC_VALIDATOR and not is_valid_deadline_candidate(
            description,
            extracted_raw_text,
            raw_source_text,
            cleaned_source_text,
        ):
            continue

        try:
            due_at_dt = datetime.strptime(due_at, "%Y-%m-%d")
        except ValueError:
            continue

        valid.append(
            {
                "description": description,
                "due_at": due_at_dt,
                "raw_text": extracted_raw_text,
            }
        )

    return valid


async def extract_deadlines(state: JournalState) -> dict:
    text = state["cleaned_text"]
    raw_text = state["raw_text"]

    prompt = build_deadline_prompt(text, raw_text)
    response = await model.ainvoke(prompt)
    content = extract_text_from_response(response)

    deadlines = parse_deadlines(
        content,
        raw_source_text=raw_text,
        cleaned_source_text=text,
    )

    return {"deadline": deadlines}