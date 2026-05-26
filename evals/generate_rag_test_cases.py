"""
One-shot generator: use Gemini 2.5 Pro to synthesise a realistic RAG test set
grounded in the test user's actual journal entries.

Output: evals/rag_test_cases.json — consumed by evals/rag_evaluation.py.

The test set is designed to be measurable across pre/post backfill of
task_type-aware embeddings, so the question and expected_entry_id (not title)
are the stable scoring keys.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()
# Bridge the Gemini-named key into Google's expected env var, same as the eval.
if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

from app.db import supabase  # noqa: E402
from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: E402

TEST_USER_ID = "97372247-26b1-42a1-9e54-76d6dfe55346"
OUT_PATH = Path(__file__).resolve().parent / "rag_test_cases.json"

pro = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0.2)


def _extract_text(response) -> str:
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # Drop the first fence line and the closing fence.
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
        if t.startswith("json"):
            t = t[4:]
    return t.strip()


PROMPT_TEMPLATE = """You are building a retrieval-quality test set for a personal journal RAG system.

Below is the COMPLETE set of journal entries for one user (chronological, newest first).
Generate exactly 30 retrieval test cases that target these entries, PLUS 4 "hard" cases.

Each test case is a JSON object with these fields:
- "question": a natural question this user might ask their journal
- "expected_entry_id": the UUID of the entry that question should retrieve, OR null
  for the no-match hard cases
- "expected_keywords": 2-4 distinctive lowercase keywords/phrases that should appear
  in any good retrieval result (drawn from the entry text; for null cases, use [])
- "category": one of "temporal", "entity", "topic", "emotional", "hard_null",
  "hard_pronoun"

Distribution requirements (TOTAL = 34):
- 8 temporal questions (e.g. "what did I do last week", "anything in May 11")
- 8 entity questions (referencing specific people/projects/places mentioned)
- 8 topic questions (referencing themes like debugging, RAG, MindGraph)
- 6 emotional/reflective questions ("when did I feel stuck", "moments of peace")
- 3 hard_null: questions about topics NOT in any entry; expected_entry_id MUST be null
- 1 hard_pronoun: a question that uses pronouns/context-dependent phrasing
  (it's fine if the question is mildly ambiguous — choose the most plausible entry)

Rules:
- expected_entry_id must be one of the IDs listed below, or null for hard_null.
- Each entry can be targeted by multiple cases. Spread coverage across the entries.
- Keywords must come from the entry's text, not invented.
- Today's date for the user is 2026-05-26. Temporal questions should make sense
  against this anchor (e.g. "last week" = 2026-05-19..05-26).
- Return STRICT JSON: a single array of 34 objects. No prose, no markdown fences.

Entries:
{entries_block}
"""


async def main() -> None:
    result = (
        supabase.table("entries")
        .select("id, auto_title, summary, cleaned_text, created_at")
        .eq("user_id", TEST_USER_ID)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    rows = result.data or []
    print(f"Loaded {len(rows)} entries for test user.")
    if len(rows) < 15:
        sys.exit(f"ABORT: need >=15 entries, got {len(rows)}.")

    entries_block_parts = []
    for row in rows:
        title = (row.get("auto_title") or "(no title)").strip()
        summary = (row.get("summary") or "").strip()
        text = (row.get("cleaned_text") or "").strip()
        # Truncate per-entry text to keep prompt size sane.
        if len(text) > 1200:
            text = text[:1200] + "..."
        entries_block_parts.append(
            f"---\n"
            f"id: {row['id']}\n"
            f"created_at: {row['created_at']}\n"
            f"title: {title}\n"
            f"summary: {summary}\n"
            f"text: {text}\n"
        )
    entries_block = "\n".join(entries_block_parts)

    prompt = PROMPT_TEMPLATE.format(entries_block=entries_block)
    print(f"Prompt size: {len(prompt)} chars. Calling Gemini 2.5 Pro...")

    response = await pro.ainvoke(prompt)
    raw = _extract_text(response)
    cleaned = _strip_json_fence(raw)

    try:
        cases = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        debug_path = OUT_PATH.with_suffix(".raw.txt")
        debug_path.write_text(raw, encoding="utf-8")
        sys.exit(f"JSON parse failed: {exc}\nRaw response dumped to {debug_path}")

    if not isinstance(cases, list):
        sys.exit(f"Expected list, got {type(cases).__name__}")

    valid_ids = {row["id"] for row in rows}
    bad = []
    for i, c in enumerate(cases):
        eid = c.get("expected_entry_id")
        if eid is not None and eid not in valid_ids:
            bad.append((i, eid))
    if bad:
        print("WARNING: cases reference unknown entry IDs:")
        for i, eid in bad:
            print(f"  case {i}: expected_entry_id={eid}")

    # Category breakdown
    by_cat: dict = {}
    for c in cases:
        cat = c.get("category", "uncategorised")
        by_cat[cat] = by_cat.get(cat, 0) + 1
    print(f"\nGenerated {len(cases)} cases:")
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat:14}: {n}")

    payload = {
        "test_user_id": TEST_USER_ID,
        "generated_with": "gemini-2.5-pro",
        "entry_count": len(rows),
        "cases": cases,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
