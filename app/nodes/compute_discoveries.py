import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db import supabase
from app.state import JournalState

logger = logging.getLogger(__name__)


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _user_entry_ids_this_month(user_id: str) -> list[str]:
    """Return IDs of completed entries for this user this month (<= 200).

    INDEX RECOMMENDATION:
      CREATE INDEX IF NOT EXISTS idx_entries_user_created_status
        ON entries(user_id, created_at DESC)
        WHERE deleted_at IS NULL AND status = 'completed';
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    result = (
        supabase.table("entries")
        .select("id")
        .eq("user_id", user_id)
        .gte("created_at", month_start)
        .is_("deleted_at", "null")
        .eq("status", "completed")
        .limit(200)
        .execute()
    )
    return [r["id"] for r in (result.data or [])]


def _pattern_recurrence(user_id: str, categories: list, entry_id: str) -> Optional[dict]:
    if not categories:
        return None

    past_ids = [eid for eid in _user_entry_ids_this_month(user_id) if eid != entry_id]
    if not past_ids:
        return None

    for category in categories:
        # INDEX RECOMMENDATION:
        #   CREATE INDEX IF NOT EXISTS idx_entry_tags_entry_category
        #     ON entry_tags(entry_id, category);
        tag_result = (
            supabase.table("entry_tags")
            .select("entry_id")
            .eq("category", category)
            .in_("entry_id", past_ids[:100])
            .execute()
        )
        count = len(tag_result.data or [])
        if count >= 2:
            n = count + 1  # include current entry
            return {
                "type": "pattern_recurrence",
                "pattern": category,
                "count": n,
                "period": "month",
                "phrase_template": "{ordinal} time you've written about {pattern} this month",
                "phrase": f"{_ordinal(n)} time you've written about {category} this month",
            }
    return None


async def _echo_from_past(
    user_id: str, embedding: list | None, entry_id: str, entity_names: list
) -> Optional[dict]:
    if not embedding:
        logger.info("echo_from_past: no embedding in state, skipping")
        return None

    try:
        # INDEX RECOMMENDATION:
        #   CREATE INDEX IF NOT EXISTS idx_entries_embedding_hnsw
        #     ON entries USING hnsw (embedding vector_cosine_ops)
        #     WITH (m = 16, ef_construction = 64);
        result = supabase.rpc(
            "match_entries",
            {"query_embedding": embedding, "match_count": 5, "filter_user_id": user_id},
        ).execute()
    except Exception as exc:
        logger.warning("echo_from_past: match_entries failed: %s", exc)
        return None

    now = datetime.now(timezone.utc)
    for match in result.data or []:
        match_id = match.get("id")
        if not match_id or match_id == entry_id:
            continue
        similarity = float(match.get("similarity", 0))
        if similarity < 0.75:
            continue

        created_at_str = match.get("created_at")
        if not created_at_str:
            row = (
                supabase.table("entries")
                .select("created_at")
                .eq("id", match_id)
                .limit(1)
                .execute()
            )
            created_at_str = (row.data or [{}])[0].get("created_at")
        if not created_at_str:
            continue

        try:
            ts = created_at_str.rstrip("Z").split("+")[0]
            created_at = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        except Exception:
            continue

        days_ago = (now - created_at).days
        if days_ago > 30:
            continue

        # Shared entity names
        shared: list[str] = []
        if entity_names:
            past_links = (
                supabase.table("entry_entities")
                .select("entity_id")
                .eq("entry_id", match_id)
                .execute()
            )
            past_ids = [r["entity_id"] for r in (past_links.data or [])]
            if past_ids:
                ent_rows = (
                    supabase.table("entities")
                    .select("name")
                    .in_("id", past_ids[:20])
                    .execute()
                )
                past_names = {r["name"].lower() for r in (ent_rows.data or [])}
                shared = [n for n in entity_names if n.lower() in past_names][:3]

        suffix = f", touching on {', '.join(shared[:2])}" if shared else ""
        day_word = "day" if days_ago == 1 else "days"
        return {
            "type": "echo_from_past",
            "days_ago": days_ago,
            "shared_entities": shared,
            "past_entry_id": match_id,
            "phrase_template": "you wrote about this {days_ago} {day_word} ago",
            "phrase": f"you wrote about this {days_ago} {day_word} ago{suffix}",
        }
    return None


def _entity_prominence(user_id: str, entity_names: list) -> Optional[dict]:
    if not entity_names:
        return None

    entry_ids = _user_entry_ids_this_month(user_id)
    if not entry_ids:
        return None

    best_name, best_count = None, 0
    for name in entity_names[:10]:
        ent_rows = (
            supabase.table("entities")
            .select("id")
            .eq("user_id", user_id)
            .ilike("name", name)
            .limit(1)
            .execute()
        )
        if not ent_rows.data:
            continue
        eid = ent_rows.data[0]["id"]
        # INDEX RECOMMENDATION:
        #   CREATE INDEX IF NOT EXISTS idx_entry_entities_entity_id
        #     ON entry_entities(entity_id);
        link_result = (
            supabase.table("entry_entities")
            .select("entry_id")
            .eq("entity_id", eid)
            .in_("entry_id", entry_ids[:100])
            .execute()
        )
        count = len(link_result.data or [])
        if count > best_count:
            best_count = count
            best_name = name

    if best_name and best_count >= 5:
        return {
            "type": "entity_prominence",
            "entity_name": best_name,
            "count": best_count,
            "period": "month",
            "phrase_template": "{entity_name} appears in {count} entries this month",
            "phrase": f"{best_name} appears in {best_count} entries this month",
        }
    return None


def _first_mention(user_id: str, core_entities: list) -> list[dict]:
    """Entities in this entry that have never appeared before (not yet in DB)."""
    results = []
    for entity in core_entities:
        if not isinstance(entity, dict):
            continue
        name = entity.get("name", "").strip()
        etype = entity.get("type", "")
        if not name:
            continue
        existing = (
            supabase.table("entities")
            .select("id")
            .eq("user_id", user_id)
            .ilike("name", name)
            .limit(1)
            .execute()
        )
        if not existing.data:
            results.append({
                "type": "first_mention",
                "entity_name": name,
                "entity_type": etype,
                "phrase_template": "first time {entity_name} appears in your journal",
                "phrase": f"first time {name} appears in your journal",
            })
        if len(results) >= 3:
            break
    return results


def _unmet_deadline_echo(user_id: str, has_deadline: bool) -> Optional[dict]:
    if not has_deadline:
        return None

    now = datetime.now(timezone.utc).isoformat()
    # TODO: completion tracking relies on deadlines.status column.
    # If the status column doesn't exist, skip this discovery type.
    try:
        result = (
            supabase.table("deadlines")
            .select("id")
            .eq("user_id", user_id)
            .lt("due_date", now)
            .neq("status", "done")
            .neq("status", "snoozed")
            .is_("deleted_at", "null")
            .execute()
        )
        count = len(result.data or [])
        if count == 0:
            return None
        plural = "s" if count != 1 else ""
        return {
            "type": "unmet_deadline_echo",
            "count": count,
            "phrase_template": "{count} past deadline{plural} still open",
            "phrase": f"{count} past deadline{plural} still open",
        }
    except Exception as exc:
        logger.info("unmet_deadline_echo skipped: %s", exc)
        return None


async def compute_discoveries(state: JournalState) -> dict:
    if state.get("dedup_check_result") == "duplicate":
        return {"discoveries": []}

    user_id = state.get("user_id", "")
    entry_id = state.get("entry_id") or ""
    categories = state.get("classifier", [])
    core_entities = state.get("core_entities", [])
    entity_names = [
        e.get("name", "") for e in core_entities if isinstance(e, dict) and e.get("name")
    ]
    embedding = state.get("entry_embedding")
    has_deadline = bool(state.get("deadline"))

    discoveries: list[dict] = []

    # Priority order: pattern_recurrence > echo_from_past > entity_prominence
    #                 > first_mention > unmet_deadline_echo
    try:
        d = _pattern_recurrence(user_id, categories, entry_id)
        if d:
            discoveries.append(d)
    except Exception as exc:
        logger.warning("pattern_recurrence failed: %s", exc)

    try:
        d = await _echo_from_past(user_id, embedding, entry_id, entity_names)
        if d:
            discoveries.append(d)
    except Exception as exc:
        logger.warning("echo_from_past failed: %s", exc)

    try:
        d = _entity_prominence(user_id, entity_names)
        if d:
            discoveries.append(d)
    except Exception as exc:
        logger.warning("entity_prominence failed: %s", exc)

    try:
        first_mentions = _first_mention(user_id, core_entities)
        for fm in first_mentions:
            if len(discoveries) >= 4:
                break
            discoveries.append(fm)
    except Exception as exc:
        logger.warning("first_mention failed: %s", exc)

    try:
        d = _unmet_deadline_echo(user_id, has_deadline)
        if d and len(discoveries) < 5:
            discoveries.append(d)
    except Exception as exc:
        logger.warning("unmet_deadline_echo failed: %s", exc)

    logger.info("compute_discoveries: %d discoveries for entry %s", len(discoveries), entry_id)
    return {"discoveries": discoveries[:5]}
