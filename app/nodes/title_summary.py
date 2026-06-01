from app.llm import flash as model
from app.state import JournalState
from app.schemas.pipeline import TitleSummary
import re

# Structured output: Gemini returns the TitleSummary shape (auto_title + summary)
# via response_json_schema, so the node no longer hand-parses JSON or strips code
# fences. method="json_schema" is explicit.
structured_model = model.with_structured_output(TitleSummary, method="json_schema")


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

- For empty or unclear input, use the title "Untitled Entry 📝" and an empty summary.

Example:
Journal Entry:
I felt really tired today but finally finished the API integration. I was stressed in the morning, but relieved by evening.

auto_title: "API Progress Relief ✅"
summary: "I felt stressed and tired early in the day, but finishing the API integration left me relieved by the evening."

Journal Entry:
{text}
"""


async def title_summary(state: JournalState) -> dict:

    text = state['raw_text']

    # Skip LLM for short entries (≤2 sentences and ≤150 chars)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    if len(sentences) <= 2 and len(text) <= 150:
        return {"auto_title": text.strip(), "summary": text.strip()}

    prompt = build_auto_title_summary_prompt(text)

    result = await structured_model.ainvoke(prompt)

    auto_title = result.auto_title.strip() or "Untitled Entry"
    summary = result.summary.strip()

    return {"auto_title": auto_title, "summary": summary}
