import os
import json
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from supabase import create_client, Client

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.3)
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def fetch_recent_entries(user_id: str, days: int = 30) -> list:
    """Fetch entries from the last N days with their tags."""
    result = supabase.rpc("get_entries_with_tags", {
        "p_user_id": user_id,
        "p_days": days
    }).execute()
    if result.data:
        return result.data

    # Fallback: plain query if RPC doesn't exist yet
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    entries = (
        supabase.table("entries")
        .select("id, raw_text, summary, auto_title, created_at")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .order("created_at", desc=False)
        .execute()
    )
    return entries.data or []


def fetch_entities(user_id: str) -> list:
    result = (
        supabase.table("entities")
        .select("id, name, entity_type, first_seen_at, last_seen_at, mention_count, context_summary")
        .eq("user_id", user_id)
        .order("mention_count", desc=True)
        .execute()
    )
    return result.data or []


def fetch_deadlines(user_id: str) -> list:
    result = (
        supabase.table("deadlines")
        .select("id, description, due_date, status, source_entry_id")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .order("due_date", desc=False)
        .execute()
    )
    return result.data or []


def fetch_tags_summary(user_id: str, days: int = 30) -> dict:
    """Get category distribution from entry_tags for recent entries."""
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    entries = (
        supabase.table("entries")
        .select("id")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .execute()
    )
    if not entries.data:
        return {}

    entry_ids = [e["id"] for e in entries.data]
    tags = (
        supabase.table("entry_tags")
        .select("category")
        .in_("entry_id", entry_ids)
        .execute()
    )
    counts = {}
    for t in (tags.data or []):
        counts[t["category"]] = counts.get(t["category"], 0) + 1
    return counts


def store_insight(user_id: str, insight_type: str, content: str, severity: str = "info") -> str:
    result = (
        supabase.table("insights")
        .insert({
            "user_id": user_id,
            "insight_type": insight_type,
            "content": content,
            "severity": severity,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        .execute()
    )
    return result.data[0]["id"] if result.data else None


# ---------------------------------------------------------------------------
# Insight generators
# ---------------------------------------------------------------------------

def generate_weekly_digest(user_id: str) -> dict:
    """
    Weekly digest: what has been on the user's mind, key themes,
    energy/mood patterns, and a one-paragraph summary.
    """
    entries = fetch_recent_entries(user_id, days=7)
    if not entries:
        return {"summary": "No entries in the last 7 days.", "themes": [], "insights": []}

    tag_counts = fetch_tags_summary(user_id, days=7)
    deadlines = fetch_deadlines(user_id)

    entries_text = "\n".join([
        f"[{e['created_at'][:10]}] {e.get('summary') or e.get('raw_text', '')[:300]}"
        for e in entries
    ])

    prompt = f"""You are analyzing a personal journal. The user wrote {len(entries)} entries this week.

ENTRIES (chronological):
{entries_text}

CATEGORY BREAKDOWN: {json.dumps(tag_counts)}

PENDING DEADLINES: {json.dumps([d['description'] for d in deadlines[:5]])}

Generate a weekly digest. Respond ONLY with a JSON object, no markdown fences:
{{
  "summary": "2-3 sentence plain-English overview of the week — what dominated the user's mind, any noticeable shifts in focus or energy",
  "themes": ["theme1", "theme2", "theme3"],
  "wins": ["something positive or progress made this week"],
  "watch": ["something worth paying attention to — not advice, just observation"],
  "entry_count": {len(entries)}
}}

Rules:
- Be factual and observational. Never give advice or emotional guidance.
- "watch" is an observation, not a recommendation. e.g. "Deadlines mentioned 3 times but no completion noted."
- Keep each string under 120 characters.
- Maximum 3 items per array."""

    response = model.invoke(prompt)
    raw = response.content.strip().replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)

    # Store in insights table
    store_insight(user_id, "weekly_digest", json.dumps(result), "info")
    return result


def generate_patterns(user_id: str) -> dict:
    """
    Pattern detection: repeated complaints, shiny object syndrome,
    recurring themes, commitment tracking.
    """
    entries = fetch_recent_entries(user_id, days=30)
    entities = fetch_entities(user_id)
    deadlines = fetch_deadlines(user_id)

    if not entries:
        return {"patterns": [], "shiny_objects": [], "repeated_themes": []}

    entries_text = "\n".join([
        f"[{e['created_at'][:10]}] {e.get('summary') or e.get('raw_text', '')[:200]}"
        for e in entries
    ])

    # Filter to interesting entities (mentioned 2+ times)
    notable_entities = [
        f"{e['name']} ({e['entity_type']}, {e['mention_count']} mentions, last: {e['last_seen_at'][:10] if e['last_seen_at'] else 'unknown'})"
        for e in entities if e['mention_count'] >= 2
    ]

    prompt = f"""You are analyzing 30 days of a personal journal.

ENTRIES ({len(entries)} total, summarized):
{entries_text}

NOTABLE ENTITIES (mentioned 2+ times):
{chr(10).join(notable_entities) if notable_entities else "None yet"}

PENDING DEADLINES: {len(deadlines)} pending

Detect behavioral patterns. Respond ONLY with JSON, no markdown fences:
{{
  "repeated_themes": [
    {{"theme": "short label", "count": 3, "observation": "factual 1-line observation"}}
  ],
  "shiny_objects": [
    {{"name": "thing they got excited about", "observation": "mentioned X times then dropped / still active"}}
  ],
  "commitment_gaps": [
    {{"observation": "factual note about commitments made vs followed through"}}
  ],
  "relationship_patterns": [
    {{"entity": "name", "observation": "factual note about interaction pattern"}}
  ]
}}

Rules:
- Only include items with actual evidence from the entries.
- Maximum 3 items per array.
- Never give advice. Only factual observations.
- If no evidence for a category, return empty array for it."""

    response = model.invoke(prompt)
    raw = response.content.strip().replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)

    store_insight(user_id, "pattern", json.dumps(result), "info")
    return result


def generate_forgotten_projects(user_id: str) -> dict:
    """
    Forgotten project detector: entities of type 'project' or high-mention
    entities that haven't been mentioned in 14+ days.
    """
    from datetime import timedelta

    entities = fetch_entities(user_id)
    now = datetime.now(timezone.utc)
    stale_threshold_days = 14

    stale = []
    active = []

    for e in entities:
        if e["mention_count"] < 2:
            continue  # skip things mentioned only once — not established yet

        last_seen_raw = e.get("last_seen_at")
        if not last_seen_raw:
            continue

        # Parse last_seen_at
        try:
            last_seen = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        days_since = (now - last_seen).days

        item = {
            "name": e["name"],
            "type": e["entity_type"],
            "mention_count": e["mention_count"],
            "days_since_mention": days_since,
            "last_mentioned": last_seen_raw[:10],
            "context": e.get("context_summary", ""),
        }

        if days_since >= stale_threshold_days:
            stale.append(item)
        else:
            active.append(item)

    # Sort stale by most recently mentioned first (closest to coming back)
    stale.sort(key=lambda x: x["days_since_mention"])

    result = {
        "stale": stale[:10],      # cap at 10
        "active": active[:10],
        "stale_count": len(stale),
        "active_count": len(active),
    }

    if stale:
        severity = "attention" if len(stale) >= 3 else "info"
        store_insight(user_id, "forgotten_projects", json.dumps(result), severity)

    return result