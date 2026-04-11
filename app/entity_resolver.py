# app/entity_resolver.py
import logging
import re
from datetime import datetime

from app.db import supabase
from app.embeddings import get_embedding

logger = logging.getLogger(__name__)


def base_normalize(text: str) -> str:
    """
    Small shared normalizer for comparison purposes.

    Safe cleanup only:
    - convert to string
    - trim outer whitespace
    - lowercase
    - collapse repeated internal whitespace

    Do NOT remove punctuation or spaces here.
    """
    value = str(text or "").strip().lower()
    value = " ".join(value.split())
    return value


def project_match_key(name: str) -> str:
    """
    Comparison-only key for project names.

    More aggressive than base_normalize, but only for projects.
    Keeps meaningful technical symbols like +, but treats dots as separators
    so variants like:
    - Node.js Migration
    - Node JS Migration
    can align.
    """
    value = base_normalize(name)
    value = re.sub(r"[._-]+", " ", value)
    value = re.sub(r"[^a-z0-9 + ]", "", value)
    value = value.replace(" ", "")
    return value


def get_match_key(name: str, entity_type: str) -> str:
    """
    Return the comparison key based on entity type.

    For now:
    - projects use project_match_key()
    - everything else uses base_normalize()
    """
    if entity_type == "project":
        return project_match_key(name)
    return base_normalize(name)


def should_accept_semantic_match(
    incoming_name: str,
    matched_name: str,
    similarity: float,
) -> bool:
    incoming = incoming_name.strip().lower()
    matched = matched_name.strip().lower()

    if similarity >= 0.95:
        return True

    if incoming in matched or matched in incoming:
        return similarity >= 0.90

    return False


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def make_entity_lookup_key(name: str, entity_type: str) -> str:
    return f"{normalize_text(name)}|{normalize_text(entity_type)}"


async def resolve_entities(entities: list[dict], user_id: str, summary: str) -> dict:
    if not entities:
        return {"ids": [], "lookup": {}}

    entity_ids: list[str] = []
    entity_lookup: dict[str, str] = {}

    for entity in entities:
        entity_name = entity["name"].strip()
        entity_type = entity["type"]
        normalized_name = entity_name.lower()
        input_lookup_key = make_entity_lookup_key(entity_name, entity_type)

        existing_same_type_resp = (
            supabase.table("entities")
            .select("id, name, entity_type, mention_count")
            .eq("user_id", user_id)
            .eq("entity_type", entity_type)
            .execute()
        )

        existing_same_type = existing_same_type_resp.data or []
        incoming_base_name = base_normalize(entity_name)

        logger.debug("Incoming entity: name=%r", entity_name)
        logger.debug("Incoming base name: %r", incoming_base_name)
        logger.debug("Existing same-type count: %d", len(existing_same_type))

        for row in existing_same_type:
            existing_name = row.get("name", "")
            existing_base_name = base_normalize(existing_name)
            logger.debug(
                "Compare existing entity: name=%r base_name=%r equal=%s",
                existing_name,
                existing_base_name,
                existing_base_name == incoming_base_name,
            )

        exact_match_row = next(
            (
                row
                for row in existing_same_type
                if base_normalize(row.get("name", "")) == incoming_base_name
            ),
            None,
        )

        if exact_match_row:
            matched = exact_match_row

            logger.info(
                "Exact match: incoming=%r normalized=%r matched=%r",
                entity_name,
                normalized_name,
                matched["name"],
            )

            supabase.table("entities").update(
                {
                    "mention_count": matched["mention_count"] + 1,
                    "last_seen_at": datetime.now().isoformat(),
                    "context_summary": summary,
                }
            ).eq("id", matched["id"]).execute()

            entity_ids.append(matched["id"])
            entity_lookup[input_lookup_key] = matched["id"]
            entity_lookup[
                make_entity_lookup_key(matched["name"], matched["entity_type"])
            ] = matched["id"]
            continue

        normalized_candidates = []

        if entity_type == "project":
            incoming_key = get_match_key(entity_name, entity_type)

            existing_projects_resp = (
                supabase.table("entities")
                .select("id, name, entity_type, mention_count")
                .eq("user_id", user_id)
                .eq("entity_type", "project")
                .execute()
            )

            existing_projects = existing_projects_resp.data or []

            normalized_candidates = [
                proj
                for proj in existing_projects
                if get_match_key(proj.get("name", ""), "project") == incoming_key
            ]

            if normalized_candidates:
                logger.info(
                    "Normalized project candidates for %r: %s",
                    entity_name,
                    [p.get("name") for p in normalized_candidates],
                )

            if len(normalized_candidates) == 1:
                matched = normalized_candidates[0]

                logger.info(
                    "Normalized project match accepted: %r -> %r",
                    entity_name,
                    matched["name"],
                )

                current_mention_count = matched.get("mention_count", 0) or 0

                supabase.table("entities").update(
                    {
                        "mention_count": current_mention_count + 1,
                        "last_seen_at": datetime.now().isoformat(),
                        "context_summary": summary,
                    }
                ).eq("id", matched["id"]).execute()

                entity_ids.append(matched["id"])
                entity_lookup[input_lookup_key] = matched["id"]
                entity_lookup[
                    make_entity_lookup_key(matched["name"], matched["entity_type"])
                ] = matched["id"]
                continue

        description = f"{entity_name} ({entity_type}) - {summary}"
        embedding = await get_embedding(description)

        match_result = supabase.rpc(
            "match_entities",
            {
                "query_embedding": embedding,
                "match_count": 3,
                "filter_user_id": user_id,
                "similarity_threshold": 0.8,
                "filter_entity_type": entity_type,
            },
        ).execute()

        if match_result.data and len(match_result.data) > 0:
            logger.debug("Candidates for %r:", entity_name)
            for match in match_result.data:
                logger.debug(
                    "Candidate: name=%r type=%s sim=%.3f",
                    match["name"],
                    match["entity_type"],
                    match["similarity"],
                )

            matched = match_result.data[0]
            similarity = matched["similarity"]

            if should_accept_semantic_match(entity_name, matched["name"], similarity):
                logger.info(
                    "Semantic match accepted: %r -> %r (type=%s, sim=%.3f)",
                    entity_name,
                    matched["name"],
                    matched["entity_type"],
                    similarity,
                )

                supabase.table("entities").update(
                    {
                        "mention_count": matched["mention_count"] + 1,
                        "last_seen_at": datetime.now().isoformat(),
                        "context_summary": summary,
                    }
                ).eq("id", matched["id"]).execute()

                entity_ids.append(matched["id"])
                entity_lookup[input_lookup_key] = matched["id"]
                entity_lookup[
                    make_entity_lookup_key(matched["name"], matched["entity_type"])
                ] = matched["id"]
            else:
                logger.info(
                    "Semantic match rejected: %r -> %r (type=%s, sim=%.3f)",
                    entity_name,
                    matched["name"],
                    matched["entity_type"],
                    similarity,
                )
                logger.info("New entity created: %s (%s)", entity_name, entity_type)

                new_entity = supabase.table("entities").insert(
                    {
                        "user_id": user_id,
                        "name": entity_name,
                        "entity_type": entity_type,
                        "first_seen_at": datetime.now().isoformat(),
                        "last_seen_at": datetime.now().isoformat(),
                        "mention_count": 1,
                        "embedding": embedding,
                        "context_summary": summary,
                    }
                ).execute()

                if new_entity.data:
                    entity_ids.append(new_entity.data[0]["id"])
                    entity_lookup[input_lookup_key] = new_entity.data[0]["id"]
        else:
            logger.info("New entity created: %s (%s)", entity_name, entity_type)

            new_entity = supabase.table("entities").insert(
                {
                    "user_id": user_id,
                    "name": entity_name,
                    "entity_type": entity_type,
                    "first_seen_at": datetime.now().isoformat(),
                    "last_seen_at": datetime.now().isoformat(),
                    "mention_count": 1,
                    "embedding": embedding,
                    "context_summary": summary,
                }
            ).execute()

            if new_entity.data:
                entity_ids.append(new_entity.data[0]["id"])
                entity_lookup[input_lookup_key] = new_entity.data[0]["id"]

    return {"ids": entity_ids, "lookup": entity_lookup}


async def store_entities(entities: list[dict], user_id: str, summary: str) -> list[str]:
    result = await resolve_entities(entities, user_id, summary)
    return result["ids"]
