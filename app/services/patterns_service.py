# app/services/patterns_service.py
"""Patterns v1 (founder-gated) — read-only aggregations over data the pipeline
already writes (docs/designs/graph-v2-patterns.md, components 1-2).

Attention Mix: per-category entry_tags counts bucketed weekly — "where your
words have been going", no targets, no ideal mix. Gravity: entity share of
entries over a 30d window with the prior window as trend — trend is data,
never good/bad.

Everything here is pull-based and behind patterns_enabled: PATTERNS_ENABLED
env flag (default OFF) OR the founder account. Trial users must see zero
difference anywhere. No schema changes, no writes.
"""
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import get_args

from app.db import supabase
from app.state import ClassifierType

logger = logging.getLogger(__name__)

# The only account that sees Patterns while PATTERNS_ENABLED is off. Gate check
# lives in patterns_enabled(); the routes 404 (not 403) so the surface stays
# invisible to trial users.
FOUNDER_USER_ID = "e7bcef72-a66c-4ebe-9c5e-0a98b5f696d8"

CATEGORIES = list(get_args(ClassifierType))

ATTENTION_WEEKS = 12
GRAVITY_WINDOW_DAYS = 30
GRAVITY_TOP_N = 5


def patterns_enabled(user_id: str) -> bool:
    """Env flag (default OFF) opens the section for everyone; otherwise only
    the founder account passes. Read per request so the flag flips without a
    restart (same kill-switch pattern as DRIFT_THRESHOLD_DAYS)."""
    flag = (os.getenv("PATTERNS_ENABLED") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    return user_id == FOUNDER_USER_ID


def _parse_ts(value):
    """Lenient timestamptz parse (same stance as intention_service): None on
    junk so one bad row never sinks the whole response."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _week_start(d: datetime):
    """Monday (UTC date) of the week containing d."""
    return (d - timedelta(days=d.weekday())).date()


async def get_attention_mix(user_id: str) -> dict:
    """Weekly per-category tag counts over the last ATTENTION_WEEKS weeks.
    Buckets are Monday-aligned UTC and always returned in full (empty weeks
    included) so the chart's x-axis is stable regardless of writing gaps."""
    now = datetime.now(timezone.utc)
    this_monday = _week_start(now)
    window_start = this_monday - timedelta(weeks=ATTENTION_WEEKS - 1)

    entries = (
        supabase.table("entries")
        .select("id, created_at")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .gte("created_at", window_start.isoformat())
        .execute()
    )
    entry_week = {}
    for row in entries.data or []:
        created = _parse_ts(row.get("created_at"))
        if created is None:
            continue
        week = _week_start(created)
        if week < window_start:
            continue
        entry_week[row["id"]] = week

    counts = defaultdict(lambda: defaultdict(int))
    tagged_entries = set()
    if entry_week:
        tags = (
            supabase.table("entry_tags")
            .select("entry_id, category")
            .in_("entry_id", list(entry_week.keys()))
            .execute()
        )
        for tag in tags.data or []:
            week = entry_week.get(tag.get("entry_id"))
            category = tag.get("category")
            if week is None or category not in CATEGORIES:
                continue
            counts[week][category] += 1
            tagged_entries.add(tag["entry_id"])

    weeks = []
    for i in range(ATTENTION_WEEKS):
        week = window_start + timedelta(weeks=i)
        weeks.append({"week_start": week.isoformat(), "counts": dict(counts.get(week, {}))})

    return {
        "categories": CATEGORIES,
        "weeks": weeks,
        "tagged_entries": len(tagged_entries),
    }


async def get_gravity(user_id: str) -> dict:
    """Top GRAVITY_TOP_N entities by share of entries mentioning them in the
    last GRAVITY_WINDOW_DAYS days, with the prior window's share as trend.
    Share = distinct entries mentioning the entity / entries in the window."""
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=GRAVITY_WINDOW_DAYS)
    prior_start = now - timedelta(days=2 * GRAVITY_WINDOW_DAYS)

    entries = (
        supabase.table("entries")
        .select("id, created_at")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .gte("created_at", prior_start.isoformat())
        .execute()
    )
    current_ids, prior_ids = set(), set()
    for row in entries.data or []:
        created = _parse_ts(row.get("created_at"))
        if created is None:
            continue
        if created >= current_start:
            current_ids.add(row["id"])
        elif created >= prior_start:
            prior_ids.add(row["id"])

    empty = {
        "window_days": GRAVITY_WINDOW_DAYS,
        "total_entries": len(current_ids),
        "prior_total_entries": len(prior_ids),
        "entities": [],
    }
    if not current_ids:
        return empty

    links = (
        supabase.table("entry_entities")
        .select("entry_id, entity_id")
        .in_("entry_id", list(current_ids | prior_ids))
        .execute()
    )
    current_mentions = defaultdict(set)
    prior_mentions = defaultdict(set)
    for link in links.data or []:
        entry_id, entity_id = link.get("entry_id"), link.get("entity_id")
        if not entity_id:
            continue
        if entry_id in current_ids:
            current_mentions[entity_id].add(entry_id)
        elif entry_id in prior_ids:
            prior_mentions[entity_id].add(entry_id)

    if not current_mentions:
        return empty

    # Name lookup is user-scoped: a link row whose entity isn't in the caller's
    # entities table (cross-user or deleted) is skipped, never shown nameless.
    names = (
        supabase.table("entities")
        .select("id, name, entity_type")
        .eq("user_id", user_id)
        .in_("id", list(current_mentions.keys()))
        .execute()
    )
    lookup = {row["id"]: row for row in names.data or []}

    ranked = []
    for entity_id, mention_ids in current_mentions.items():
        entity = lookup.get(entity_id)
        if not entity:
            continue
        prior_count = len(prior_mentions.get(entity_id, set()))
        ranked.append(
            {
                "entity_id": entity_id,
                "name": entity.get("name"),
                "entity_type": entity.get("entity_type"),
                "entry_count": len(mention_ids),
                "share": round(len(mention_ids) / len(current_ids), 4),
                "prior_share": round(prior_count / len(prior_ids), 4) if prior_ids else 0,
            }
        )
    ranked.sort(key=lambda e: (-e["share"], e["name"] or ""))

    return {
        "window_days": GRAVITY_WINDOW_DAYS,
        "total_entries": len(current_ids),
        "prior_total_entries": len(prior_ids),
        "entities": ranked[:GRAVITY_TOP_N],
    }
