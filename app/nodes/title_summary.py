from app.state import JournalState
from datetime import datetime
import re, os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import get_args, List
import json
load_dotenv()

os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.1)



def build_auto_title_summary_prompt(text: str) -> str:
    return f"""
You are a journal assistant that generates an automatic title and summary for a personal journal entry.

Task:
Read the journal entry and produce:
1) a short, meaningful title
2) a brief summary

Requirements:
- The title must be concise (3 to 8 words; 4 to 6 preferred).
- The title should reflect the main theme, event, or emotion.
- Avoid generic titles like "Journal Entry", "My Day", or "Today".
- Prefer specific, emotionally meaningful titles over generic phrasing.
- Avoid filler-heavy titles unless necessary (e.g., unnecessary "A", "The", "and").
- The title must include exactly 1 relevant emoji.
- Place the emoji naturally in the title (start or end).
- The emoji should reflect the main emotion or event.
- Do not use multiple emojis or decorative emoji spam.

- The summary must be concise and natural.
- Prefer a single-sentence summary; use two sentences only if needed for clarity.
- Target 18 to 30 words (hard limit: 40 words).
- The summary should capture the key event(s), feeling(s), or reflection(s).
- Do not invent details that are not in the journal entry.
- If the entry is unclear or too short, infer conservatively and still provide a useful title and summary.
- For very short journal entries, keep the summary especially simple and avoid over-expanding.
- Do not include quotes unless they appear in the entry.
- Do not use emojis in the summary.
- Avoid repetitive wording in the summary.

- Preserve the original language of the journal entry (if not English, respond in that language).
- Write the summary in first-person ("I") when the journal entry is written in first-person.
- Do not rewrite the summary in second-person ("you").

Output Rules:
- Return STRICT JSON only.
- No markdown, no code fences, no explanation, no extra text.
- Use exactly these keys: "auto_title", "summary"

Fallback for empty or unclear input:
{{"auto_title":"Untitled Entry 📝","summary":""}}

Expected JSON format:
{{
  "auto_title": "string",
  "summary": "string"
}}

Example:
Journal Entry:
I felt really tired today but finally finished the API integration. I was stressed in the morning, but relieved by evening.

Output:
{{"auto_title":"API Progress Relief ✅","summary":"I felt stressed and tired early in the day, but finishing the API integration left me relieved by the evening."}}

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

def parse_JSON(raw: str) -> tuple[str, str]:
    # Remove markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "Untitled Entry", ""

    if not isinstance(data, dict):
        return "Untitled Entry", ""

    auto_title = data.get("auto_title", "")
    summary = data.get("summary", "")

    if not isinstance(auto_title, str):
        auto_title = ""
    if not isinstance(summary, str):
        summary = ""

    auto_title = auto_title.strip() or "Untitled Entry"
    summary = summary.strip()

    return auto_title, summary


async def title_summary(state: JournalState) -> dict:

    text = state['raw_text']

    # Skip LLM for short entries (≤2 sentences and ≤150 chars)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    if len(sentences) <= 2 and len(text) <= 150:
        return {"auto_title": text.strip(), "summary": text.strip()}

    prompt = build_auto_title_summary_prompt(text)

    response = await model.ainvoke(prompt)

    content = extract_text_from_response(response)

    auto_title,summary = parse_JSON(content)

    return {"auto_title": auto_title, "summary": summary}



