from app.state import JournalState,CoreEntityNode,EntityType,DeadlineNode
from datetime import datetime
import re, os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import get_args, List
import json
load_dotenv()

os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.1)



def build_deadline_prompt(text: str, raw_text: str) -> str:
    reference_date = datetime.now().strftime("%Y-%m-%d")
    return f"""
You are a deadline extraction engine.

Extract all explicit or implied deadlines from the journal entry.

Reference Date:
{reference_date}

Cleaned Input:
{text}

Raw Input:
{raw_text}

Output Rules:
- Return STRICT JSON only.
- No markdown, no code fences, no explanation.
- Return a JSON array.
- If no deadlines exist, return [].
- Use exactly these keys for each item: "description", "due_at", "raw_text"
- "description" = short description of what the deadline is for
- "due_at" = date in YYYY-MM-DD format
- "raw_text" = the exact deadline phrase from the journal text (e.g., "tomorrow", "next Monday")
- Resolve relative dates (e.g., "tomorrow", "next week", "Friday") using the Reference Date.
- Do not include extra fields.
- Do not invent deadlines that are not in the text.
- If a date is ambiguous and cannot be resolved confidently, skip it.

Format:
[
  {{"description": "deadline description", "due_at": "YYYY-MM-DD", "raw_text": "deadline phrase"}}
]
"""

def extract_text_from_response(response):
    content = response.content

    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )

    return content.strip()

def parse_deadlines(raw: str) -> list[DeadlineNode]:
    raw = raw.strip()

    # Remove markdown code fences if present
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
        raw_text = item.get("raw_text")

        if not all(isinstance(x, str) for x in [description, due_at, raw_text]):
            continue

        description = description.strip()
        due_at = due_at.strip()
        raw_text = raw_text.strip()

        if not description:
            continue

        # Validate date string format first
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_at):
            continue

        # Convert YYYY-MM-DD string to datetime
        try:
            due_at_dt = datetime.strptime(due_at, "%Y-%m-%d")
        except ValueError:
            continue

        valid.append(
            {
                "description": description,
                "due_at": due_at_dt,
                "raw_text": raw_text,
            }
        )

    return valid


async def extract_deadlines(state: JournalState) -> dict:
    

    text = state['cleaned_text']
    raw_text = state['raw_text']


    prompt = build_deadline_prompt(text, raw_text)

    response = await model.ainvoke(prompt)

    content = extract_text_from_response(response)

    deadlines = parse_deadlines(content)

    return {"deadline": deadlines}



