import hashlib
import logging
from datetime import datetime, timedelta, timezone

from app.db import supabase
from app.state import JournalState

logger = logging.getLogger(__name__)

_PIPELINE_VERSION = "v2.2.0"


def _pipeline_hash() -> str:
    return hashlib.sha1(_PIPELINE_VERSION.encode()).hexdigest()[:8]


def _first_mention_names(user_id: str) -> set[str]:
    """Return lowercase entity names created in the last 90 seconds (this pipeline run)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
    try:
        result = (
            supabase.table("entities")
            .select("name")
            .eq("user_id", user_id)
            .gte("created_at", cutoff)
            .execute()
        )
        return {r["name"].lower() for r in (result.data or [])}
    except Exception as exc:
        logger.warning("assemble_dispatch: first_mention_names failed: %s", exc)
        return set()


async def assemble_dispatch(state: JournalState) -> dict:
    entry_id = state.get("entry_id")

    if state.get("dedup_check_result") == "duplicate":
        if entry_id:
            try:
                supabase.table("entries").update(
                    {"status": "completed", "pipeline_stage": None}
                ).eq("id", str(entry_id)).execute()
            except Exception:
                pass
        return {}

    if not entry_id:
        return {}

    user_id = state.get("user_id", "")
    title = state.get("auto_title", "") or ""
    summary = state.get("summary", "") or ""
    discoveries: list[dict] = list(state.get("discoveries", []))
    core_entities: list[dict] = state.get("core_entities", []) or []
    categories: list[str] = state.get("classifier", []) or []
    deadline: list[dict] = state.get("deadline", []) or []

    new_names = _first_mention_names(user_id)

    stamps: list[dict] = []

    # Deadline stamps
    for d in deadline:
        if not isinstance(d, dict):
            continue
        desc = (d.get("description") or "").strip()
        due = str(d.get("due_at") or d.get("due_date") or "").strip()
        val = f"{desc} -- {due}" if desc and due else desc or due
        if val:
            stamps.append({
                "kind": "deadline",
                "label": "DEADLINE",
                "value": val,
                "editable": True,
                "original_value": val,
            })

    # Mood stamp from emotional/personal categories
    mood_cats = {"personal", "health", "family", "hobby"}
    mood_val = next((c for c in categories if c in mood_cats), None)
    if mood_val:
        stamps.append({
            "kind": "mood",
            "label": "MOOD",
            "value": mood_val,
            "editable": True,
            "original_value": mood_val,
        })

    # Entity stamps by type
    type_to_kind = {
        "person": "person",
        "project": "project",
        "tool": "topic",
        "organization": "topic",
        "event": "topic",
        "task": "topic",
        "place": "topic",
    }
    person_cap = project_cap = topic_cap = 3
    for entity in core_entities:
        if not isinstance(entity, dict):
            continue
        name = (entity.get("name") or "").strip()
        etype = entity.get("type", "")
        kind = type_to_kind.get(etype)
        if not kind or not name:
            continue

        if kind == "person" and person_cap > 0:
            person_cap -= 1
        elif kind == "project" and project_cap > 0:
            project_cap -= 1
        elif kind == "topic" and topic_cap > 0:
            topic_cap -= 1
        else:
            continue

        is_first = name.lower() in new_names
        stamps.append({
            "kind": kind,
            "label": kind.upper(),
            "value": name,
            "editable": True,
            "original_value": name,
            "is_first_mention": is_first,
        })

    # Pattern stamps from remaining categories (non-mood)
    for cat in categories[:2]:
        if cat not in mood_cats:
            stamps.append({
                "kind": "pattern",
                "label": "PATTERN",
                "value": cat,
                "editable": True,
                "original_value": cat,
            })

    # Inject first_mention discoveries for new entities not already in discoveries list
    discovery_types_present = {d.get("type") for d in discoveries}
    if "first_mention" not in discovery_types_present:
        for entity in core_entities:
            if not isinstance(entity, dict):
                continue
            name = (entity.get("name") or "").strip()
            etype = entity.get("type", "")
            if name.lower() in new_names and len(discoveries) < 5:
                discoveries.append({
                    "type": "first_mention",
                    "entity_name": name,
                    "entity_type": etype,
                    "phrase_template": "first time {entity_name} appears in your journal",
                    "phrase": f"first time {name} appears in your journal",
                })
                break

    dispatch_payload = {
        "subject": title,
        "summary": summary,
        "discoveries": discoveries[:5],
        "stamps": stamps,
        "pipeline_version": _pipeline_hash(),
        "entry_id": str(entry_id),
    }

    # DEBUG: track the exact payload size + shape we're about to send.
    try:
        import json as _json
        dp_size = len(_json.dumps(dispatch_payload, default=str))
    except Exception:
        dp_size = -1
    logger.info(
        "assemble_dispatch: writing dp size=%dB keys=%s for entry %s",
        dp_size, list(dispatch_payload.keys()), entry_id,
    )

    try:
        res = supabase.table("entries").update({
            "dispatch_payload": dispatch_payload,
            "status": "completed",
            "pipeline_stage": None,
        }).eq("id", str(entry_id)).execute()

        # DEBUG: did the UPDATE actually persist dispatch_payload?
        returned_dp = None
        if res.data and len(res.data) > 0:
            returned_dp = res.data[0].get("dispatch_payload")
        logger.info(
            "assemble_dispatch: UPDATE returned rows=%d, returned_dp_type=%s for entry %s",
            len(res.data) if res.data else 0,
            type(returned_dp).__name__,
            entry_id,
        )

        # DEBUG: immediate re-read to confirm what's actually in the column post-write
        try:
            verify = (
                supabase.table("entries")
                .select("dispatch_payload, status, pipeline_stage")
                .eq("id", str(entry_id))
                .single()
                .execute()
            )
            v = verify.data or {}
            v_dp = v.get("dispatch_payload")
            logger.info(
                "assemble_dispatch: POST-WRITE verify dp_type=%s status=%s stage=%s for entry %s",
                type(v_dp).__name__,
                v.get("status"),
                v.get("pipeline_stage"),
                entry_id,
            )
        except Exception as verify_exc:
            logger.warning("assemble_dispatch: post-write verify failed: %s", verify_exc)
    except Exception as exc:
        logger.error(
            "assemble_dispatch: failed to persist dispatch_payload for entry %s: %s",
            entry_id, exc, exc_info=True,
        )
        try:
            supabase.table("entries").update(
                {"status": "error", "pipeline_stage": None}
            ).eq("id", str(entry_id)).execute()
        except Exception:
            pass

    return {"dispatch_payload": dispatch_payload}
