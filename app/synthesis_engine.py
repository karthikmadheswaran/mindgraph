"""
app/synthesis_engine.py — the Reflection feature's self-synthesis ENGINE (Phase 1).

WHAT / WHY
----------
Maintains a per-user, single-row EVOLVING "self-understanding" document in the
user_synthesis table (migration 019). Each run reads (existing doc + the person's
REAL journal entries since the watermark) and REWRITES a bounded doc that surfaces
NON-OBVIOUS behavioural/psychological patterns the person never explicitly stated
("you tend to leave the moment things get uncomfortable"), rather than the shallow
mention-count bookkeeping the old generate_patterns produced.

This is deliberately SEPARATE from insights_engine.generate_patterns (the shallow
generator) so the two never entangle. It is a near-clone of the proven Ask memory
compaction loop (compact_old_messages / build_compaction_prompt): read existing
blob -> feed new evidence -> LLM rewrite -> upsert on_conflict="user_id".

Distinct from drift (intentions table): reflection = who the person IS across their
writing; drift = stated-intention-vs-behaviour gaps. The prompt forbids drift
framing so the two features stay in their lanes.

PHASE 1 SCOPE: generate + inspect output only. NOT wired into the per-entry trigger,
NO cadence/debounce gate, NO gift UX. Run it manually to read the output:

    python -m app.synthesis_engine <user_id>                 # incremental (watermark)
    python -m app.synthesis_engine <user_id> --reprocess-all # re-fold the whole journal

The synthesis doc contains the user's private journal-derived text; the CLI prints
it to stdout only and writes NO files.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.db import supabase
from app.llm import pro as model

logger = logging.getLogger(__name__)

# Cap the number of insights the doc may hold. Enforced in the prompt; this constant
# is the single source of truth so the eval and the prompt agree.
MAX_INSIGHTS = 7

# Cadence (debounced-on-entry, NOT a scheduler): regenerate at most once every
# REFLECTION_STALE_DAYS, and only when there are new entries to fold. The very first
# gift also needs at least REFLECTION_MIN_ENTRIES so it isn't thin. Both env-tunable,
# mirroring DRIFT_THRESHOLD_DAYS.
REFLECTION_STALE_DAYS = int(os.getenv("REFLECTION_STALE_DAYS", "3"))
REFLECTION_MIN_ENTRIES = int(os.getenv("REFLECTION_MIN_ENTRIES", "5"))


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------

def fetch_synthesis_row(user_id: str) -> dict | None:
    """The user's current synthesis row, or None on first run."""
    result = (
        supabase.table("user_synthesis")
        .select("synthesis_text, last_processed_at, generated_at, updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def fetch_new_entries(user_id: str, since: str | None) -> list:
    """Completed, non-deleted entries oldest-first. If `since` is set, only entries
    created after the watermark (the incremental path). FULL raw_text — never
    truncated (the 200-char cap in the old engine was a root cause of shallowness)."""
    query = (
        supabase.table("entries")
        .select("id, raw_text, created_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
    )
    if since:
        query = query.gt("created_at", since)
    query = query.order("created_at", desc=False)
    return query.execute().data or []


def fetch_tags_for_entries(entry_ids: list) -> dict:
    """entry_id -> [category, ...]. Light topical grounding for emotional-cadence
    claims. NOTE: this is category labels only — NOT a mention-count list (that
    list is the documented cause of shallow output and is deliberately absent)."""
    if not entry_ids:
        return {}
    result = (
        supabase.table("entry_tags")
        .select("entry_id, category")
        .in_("entry_id", entry_ids)
        .execute()
    )
    tags: dict = {}
    for row in result.data or []:
        tags.setdefault(row["entry_id"], []).append(row["category"])
    return tags


# ---------------------------------------------------------------------------
# Formatting + prompt
# ---------------------------------------------------------------------------

def format_entries_block(entries: list, tags: dict) -> str:
    """One block per entry: date, optional category tags, then the person's FULL
    words. Entry boundaries are explicit so the model can reason across entries."""
    blocks = []
    for e in entries:
        date = (e.get("created_at") or "")[:10]
        cats = tags.get(e.get("id")) or []
        cat_line = f" (categories: {', '.join(cats)})" if cats else ""
        text = (e.get("raw_text") or "").strip()
        blocks.append(f"[{date}]{cat_line}\n{text}")
    return "\n\n---\n\n".join(blocks)


def build_synthesis_prompt(existing_synthesis: str, entries_block: str) -> str:
    """Build the reflection prompt. Separated from the LLM call so the deterministic
    eval can assert on it without a network call (mirrors build_compaction_prompt)."""
    parts = [
        "# Role",
        "You are a rare kind of reader: someone who has read every word of another "
        "person's private journal, slowly, and can see the patterns they cannot see "
        "in themselves. You are perceptive, honest, and warm — never clinical, never "
        "a therapist, never a diagnostician.",
        "",
        "# Objective",
        "Maintain an evolving SELF-UNDERSTANDING document for this person. Read their "
        "real journal entries below (their own words) together with the existing "
        "self-understanding document, and produce an UPDATED document that reveals "
        "NON-OBVIOUS behavioural and psychological patterns they have never explicitly "
        "stated about themselves.",
        "The test for every line: would the person read it and think 'I never realised "
        "I do that — but it's true'? If it only tells them something they already know, "
        "it does not belong.",
        "",
        "# What a real insight looks like",
        "- 'You tend to leave situations the moment they become uncomfortable, then "
        "reframe the exit as a considered decision.'",
        "- 'You start something new when you're avoiding something harder — new ideas "
        "cluster right after the entries where you sound most stuck.'",
        "- 'Your writing gets short and clipped in the days before you mention family.'",
        "Each insight names a pattern in HOW they think, feel, or behave across entries "
        "— something visible only from reading all of it, grounded in what the entries "
        "actually show.",
        "",
        "# Forbidden — these are the shallow failures this feature exists to avoid",
        "- Do NOT count occurrences or report tallies (no 'came up N times', no "
        "frequencies, no 'repeatedly').",
        "- Do NOT do recency bookkeeping (no 'last written about on <date>', no "
        "'active/stale', no 'hasn't come up since').",
        "- Do NOT restate obvious topics or summarise what they wrote. They already "
        "know what they wrote about. Reveal, don't summarise.",
        "- Do NOT give advice, encouragement, or next steps. Observe who they are; do "
        "not coach.",
        "- Do NOT diagnose or use clinical / therapy-speak.",
        "",
        "# Stay in your lane (distinct from the separate 'drift' feature)",
        "- This document is about who the person IS across their writing — their "
        "tendencies, contradictions, emotional rhythms, the shape of their attention.",
        "- Do NOT frame insights as 'you said you'd do X and didn't' or 'commitments "
        "made vs followed through'. Stated-intention-vs-behaviour gaps are handled "
        "elsewhere. Stay on character and pattern, not accountability.",
        "",
        "# Grounding",
        "- Every insight must be supported by what the entries actually show. Prefer "
        "patterns visible across MULTIPLE entries over a single dramatic line.",
        "- You may briefly paraphrase or quote a few of their own words as evidence, "
        "but keep the focus on the pattern, not the quote.",
        "",
        "# Bounded document discipline (as important as the insight itself)",
        "- Treat the EXISTING self-understanding document as a DRAFT TO REWRITE, not "
        "something to preserve by default.",
        "- Merge new evidence into existing observations. STRENGTHEN patterns that "
        "recur in the new entries; SOFTEN or DROP observations the new entries weaken "
        "or fail to support.",
        f"- Keep only the STRONGEST insights — at most {MAX_INSIGHTS}. If a new insight "
        "is stronger than an existing one, replace it. The document must NOT grow "
        "longer over time; it must get truer.",
        "- NEVER keep both a stale and an updated version of the same insight. No "
        "duplicates, no near-duplicates.",
        "",
        "# Existing self-understanding document",
        existing_synthesis.strip() if existing_synthesis.strip()
        else "(none yet — this is the first pass)",
        "",
        "# The person's journal entries (their own words)",
        entries_block.strip() if entries_block.strip() else "(none)",
        "",
        "# Output contract",
        "- Output ONLY the updated self-understanding document as plain markdown.",
        f"- At most {MAX_INSIGHTS} insights. Each insight: a short bold title line, "
        "then one to three sentences naming the pattern and its grounding.",
        "- No preamble, no closing, no rationale, no notes about what you changed, no "
        "code fences.",
        "- Write in second person ('you'), calm and direct.",
    ]
    return "\n".join(parts)


def build_prompt_for_user(user_id: str, reprocess_all: bool = False) -> tuple[str, list]:
    """Fetch + format + build the prompt for a user. Returns (prompt, entries).
    No LLM call — this is the seam the deterministic eval drives against a fake DB."""
    row = fetch_synthesis_row(user_id)
    existing = (row or {}).get("synthesis_text", "") or ""
    watermark = None if reprocess_all else (row or {}).get("last_processed_at")

    entries = fetch_new_entries(user_id, watermark)
    tags = fetch_tags_for_entries([e["id"] for e in entries])
    block = format_entries_block(entries, tags)
    return build_synthesis_prompt(existing, block), entries


# ---------------------------------------------------------------------------
# Generation (read-modify-write) — clone of the memory compaction loop
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Defensive: the output contract forbids code fences, but strip a wrapping
    ```-fence if the model adds one anyway."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def generate_synthesis(user_id: str, reprocess_all: bool = False) -> dict:
    """Read the existing doc + new entries, rewrite a bounded self-understanding
    document, and upsert it. Returns a summary dict (incl. the new text).

    reprocess_all=True re-folds the WHOLE journal (ignores the watermark) — used for
    the Phase-1 manual second pass, so consolidation/rewrite behaviour is visible
    even with no brand-new entries between runs."""
    row = fetch_synthesis_row(user_id)
    existing = (row or {}).get("synthesis_text", "") or ""

    prompt, entries = build_prompt_for_user(user_id, reprocess_all=reprocess_all)
    if not entries:
        return {
            "status": "no_new_entries",
            "synthesis_text": existing,
            "entries_folded": 0,
        }

    response = model.invoke(prompt)
    new_text = _strip_fences(response.content)

    new_watermark = max(e["created_at"] for e in entries)
    now = datetime.now(timezone.utc).isoformat()
    (
        supabase.table("user_synthesis")
        .upsert(
            {
                "user_id": user_id,
                "synthesis_text": new_text,
                "last_processed_at": new_watermark,
                "generated_at": now,
                "updated_at": now,
                # Re-wrap the gift: a freshly generated reflection is unopened, so the
                # UX shows it "wrapped" again until the user reveals it.
                "opened_at": None,
            },
            on_conflict="user_id",
        )
        .execute()
    )

    usage = getattr(response, "usage_metadata", None)
    return {
        "status": "ok",
        "synthesis_text": new_text,
        "entries_folded": len(entries),
        "last_processed_at": new_watermark,
        "had_existing_doc": bool(existing.strip()),
        "usage": usage,
    }


# ---------------------------------------------------------------------------
# Cadence: debounced-on-entry regeneration (no scheduler)
# ---------------------------------------------------------------------------

def _is_stale(row: dict | None) -> bool:
    """True when the doc is old enough to refresh (or doesn't exist yet)."""
    if not row:
        return True
    stamp = row.get("generated_at") or row.get("updated_at")
    if not stamp:
        return True
    try:
        ts = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    return (datetime.now(timezone.utc) - ts) >= timedelta(days=REFLECTION_STALE_DAYS)


def maybe_regenerate_synthesis(user_id: str) -> dict:
    """Gated regeneration: run generate_synthesis ONLY when the doc is stale
    (older than REFLECTION_STALE_DAYS, or absent) AND there are new entries to fold.
    The first-ever gift additionally needs REFLECTION_MIN_ENTRIES so it isn't thin.
    Cheap DB reads short-circuit before any LLM call — safe to call after every entry."""
    row = fetch_synthesis_row(user_id)
    if not _is_stale(row):
        return {"status": "skipped_fresh"}

    watermark = (row or {}).get("last_processed_at")
    new_entries = fetch_new_entries(user_id, watermark)
    if not new_entries:
        return {"status": "skipped_no_new_entries"}
    if not row and len(new_entries) < REFLECTION_MIN_ENTRIES:
        return {"status": "skipped_too_few_entries", "count": len(new_entries)}

    return generate_synthesis(user_id, reprocess_all=False)


async def maybe_regenerate_synthesis_bg(user_id: str) -> None:
    """Fire-and-forget wrapper for the entry pipeline. Runs the (blocking, sync)
    gate + LLM call in a worker thread so it never blocks the event loop or the
    entry response. Swallows errors — a failed reflection must never fail an entry."""
    try:
        result = await asyncio.to_thread(maybe_regenerate_synthesis, user_id)
        logger.info("reflection synthesis: %s (user %s)", result.get("status"), user_id)
    except Exception as exc:
        logger.error("reflection synthesis regen failed for %s: %s", user_id, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Manual runner (Phase 1 — read the output; writes NO files)
# ---------------------------------------------------------------------------

def _approx_tokens(text: str) -> int:
    return len(text) // 4  # rough; good enough to confirm the doc stays bounded


def _main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    reprocess_all = "--reprocess-all" in argv
    if not args:
        print("usage: python -m app.synthesis_engine <user_id> [--reprocess-all]")
        return 2
    user_id = args[0]

    result = generate_synthesis(user_id, reprocess_all=reprocess_all)

    print("=" * 72)
    print(f"SYNTHESIS  user={user_id}  reprocess_all={reprocess_all}")
    print(f"status={result['status']}  entries_folded={result['entries_folded']}  "
          f"had_existing_doc={result.get('had_existing_doc')}")
    print("=" * 72)
    text = result.get("synthesis_text", "") or ""
    print(text)
    print("-" * 72)
    print(f"chars={len(text)}  words={len(text.split())}  approx_tokens={_approx_tokens(text)}")
    if result.get("usage"):
        print(f"usage={result['usage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
