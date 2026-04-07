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
You are a strict entity extraction engine.

Extract only concrete, meaningful named entities from the journal entry.
Allowed types: {allowed_types_str}

Return STRICT JSON only. No explanation.
Format:
[
  {{"name": "entity_name", "type": "entity_type"}}
]

Rules:
- Use only these types: {allowed_types_str}
- If no valid entities exist, return []
- Do not include extra fields
- Extract only entities that are specific and meaningful in context
- Do not guess or infer entities that are not clearly mentioned

Never extract:
- dates, times, timestamps, years, months, weekdays
- generic nouns like "project", "conversation", "meeting", "task", "work"
- vague concepts like "life", "mind", "thoughts", "feelings", "my own mind"
- pronouns or generic references like "I", "me", "someone", "my friend"
- generic role/document words: "proposal", "team", "council", "review", "group" as standalone names (these are only valid when embedded in a full proper name like "Surrey County Council")
- sentence fragments
- duplicate entities
- anything with type "none"

Entity guidance:
- person: a specific person's name or uniquely identified person
- project: a clearly named app, product, initiative, workstream, feature build, client engagement, or ongoing effort; do not use "project" for unfamiliar capitalized words unless the surrounding text clearly shows building, working on, planning, designing, shipping, fixing, or discussing that named effort; if unsure, omit
- tool: a specific software, framework, platform, data format, or device that is actively used, tested, or built with in this entry; when comparing two tools ("tested X to compare it with Y"), extract only X (the one being tested), not Y (the baseline); data formats and open table formats (e.g. Delta Lake, Parquet, Iceberg) are tools
- place: a specific location, city, office, venue, or geographic place
- organization: a company, institution, university, or brand; named teams like "Google Cloud" qualify, but generic noun phrases like "the council team", "the internal team", "the leadership group", or bare "council" without a specific name (e.g. not "Surrey County Council") are not organizations — omit them entirely
- event: a specific named event, appointment, or occasion
- task: a specific actionable item, not a generic word

Normalization rules:
- Keep names concise
- Remove filler words unless they are part of the real name
- Prefer "MindGraph" over "my MindGraph project"
- Prefer singular canonical names
- Strip trailing UI/feature words from project names: do not include "onboarding", "dashboard", "auth", "screen", "module", "page", "settings", "flow" as part of the name — extract only the root (e.g. "Velora" not "Velora dashboard", "mindgraph" not "mindgraph auth page")
- Do not extract sub-strings from compound entity names (e.g. do not extract "Surrey" from "SurreyCare" — the full compound is the entity)

Project disambiguation rules:
- Do not use "project" as a fallback for unfamiliar capitalized words.
- A capitalized or brand-like word is only a project if the surrounding text clearly shows it is something being built, worked on, planned, designed, launched, shipped, fixed, or discussed as an ongoing named effort.
- Omit any brand-like word that appears only in a mental, personal, or medical context. Do NOT classify it as project or tool. This includes: taking medicine ("I took X"), mental preoccupation ("thinking about X", "X came up in my mind", "I kept thinking about X"), or a passing thought ("it was just a passing thought about X").
- For tools: only extract a word if you recognize it as a real, existing technology from your knowledge. An unfamiliar word in a usage context ("I used X to generate/create/design") may refer to the user's own project or a niche/fictional product — omit it if you do not know it. Contrast: "I used Figma to design" → extract Figma (recognized tool); "I used Velora to generate wireframes" → omit Velora (not a known technology).
- If the context is unclear, omit rather than guessing "project".

Task disambiguation rules:
- Use "task" only for a specific actionable deliverable or work item phrase.
- Good task examples: "provider renewal summary", "quarterly provider report", "quality assurance report", "migration notes", "release notes".
- Do not extract generic verbs or vague actions like "finish", "send", "review", "work", or "meeting" as tasks.
- Prefer the concrete deliverable name, not the action around it.

Examples of invalid outputs:
- {{"name": "2026-03-31", "type": "event"}}
- {{"name": "project", "type": "project"}}
- {{"name": "conversation", "type": "event"}}
- {{"name": "my own mind", "type": "none"}}
- {{"name": "Inspiral", "type": "tool"}}  (personal/medical context: "I took Inspiral")
- {{"name": "Inspiral", "type": "project"}}  (reflective context: "came up in my mind")
- {{"name": "Velora", "type": "project"}}  (reflective: "kept thinking about Velora")
- {{"name": "Velora", "type": "tool"}}  (from "I used Velora to generate wireframes": Velora is not a known technology — omit unrecognized words even in usage context)
- {{"name": "Claude", "type": "tool"}}  (comparison only: "compare it with Claude")
- {{"name": "council", "type": "organization"}}  (from "council team": stripping "team" leaves "council" which is also generic — omit entirely)
- {{"name": "Google proposal", "type": "task"}}  (do not combine org name with generic document word; extract "Google" as org and omit "proposal")

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



