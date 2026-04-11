import json
from typing import get_args

from app.llm import extract_text, flash as model
from app.state import EntityType, JournalState, RelationEdge, RelationType

ENTITY_TYPES = set(get_args(EntityType))
RELATION_TYPES = tuple(get_args(RelationType))
RELATION_TYPES_STR = ", ".join(RELATION_TYPES)


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def make_entity_key(name: str, entity_type: str) -> str:
    return f"{normalize_text(name)}|{normalize_text(entity_type)}"


def build_relations_prompt(text: str, entities: list[dict]) -> str:
    entity_list = "\n".join(
        f'- "{entity["name"]}" ({entity["type"]})'
        for entity in entities
    )

    return f"""
You are a strict semantic relationship extraction engine for a personal journal.

Given a journal entry and its extracted entities, identify only meaningful semantic
relationships between the entities.

Valid relation types: {RELATION_TYPES_STR}

Direction rules:
- uses: person/organization/project -> tool
- built_with: project -> tool
- works_on: person -> project/task
- works_with: person <-> person or person <-> organization
- located_at: person/project/organization/event/task -> place
- belongs_to: entity -> organization/project
- part_of: smaller entity -> larger entity

Critical rules:
- Do not extract co-occurrence.
- "I talked to Sachin. Also worked on MindGraph." -> no relationship.
- "I used Claude to build MindGraph." -> MindGraph(project) built_with Claude(tool) or I(person) uses Claude(tool) only if both entities are present.
- "Met Sachin at Inspiral office." -> Sachin(person) located_at Inspiral office(place).
- Use only entity names and types from the provided list.
- Return [] if no clear semantic relationship exists.
- Never create self-relations.
- Maximum 5 relations.
- If the relation is ambiguous, drop it.

Entities in this entry:
{entity_list}

Return STRICT JSON only. No explanation.
Format:
[
  {{
    "source": "entity_name",
    "source_type": "entity_type",
    "target": "entity_name",
    "target_type": "entity_type",
    "relation": "relation_type"
  }}
]

Journal Entry:
{text}
"""


def is_valid_relation_direction(
    relation_type: str,
    source_type: str,
    target_type: str,
) -> bool:
    if relation_type == "uses":
        return source_type in {"person", "organization", "project"} and target_type == "tool"

    if relation_type == "built_with":
        return source_type == "project" and target_type == "tool"

    if relation_type == "works_on":
        return source_type == "person" and target_type in {"project", "task"}

    if relation_type == "works_with":
        return source_type == "person" and target_type in {"person", "organization"}

    if relation_type == "located_at":
        return source_type in {"person", "project", "organization", "event", "task"} and target_type == "place"

    if relation_type == "belongs_to":
        return source_type in ENTITY_TYPES - {"none"} and target_type in {"organization", "project"}

    if relation_type == "part_of":
        return source_type in ENTITY_TYPES - {"none"} and target_type in {"project", "organization", "event", "place"}

    return False


def canonicalize_relations(relations: list[RelationEdge]) -> list[RelationEdge]:
    deduped: dict[tuple[str, str, str, str, str], RelationEdge] = {}

    for relation in relations:
        source_name = relation["source"]
        source_type = relation["source_type"]
        target_name = relation["target"]
        target_type = relation["target_type"]

        if relation["relation"] == "works_with":
            endpoints = sorted(
                [
                    (normalize_text(source_name), source_name, source_type),
                    (normalize_text(target_name), target_name, target_type),
                ],
                key=lambda item: item[0],
            )
            (_, source_name, source_type), (_, target_name, target_type) = endpoints

        key = (
            make_entity_key(source_name, source_type),
            make_entity_key(target_name, target_type),
            relation["relation"],
            source_type,
            target_type,
        )

        deduped[key] = {
            "source": source_name,
            "source_type": source_type,
            "target": target_name,
            "target_type": target_type,
            "relation": relation["relation"],
        }

    return list(deduped.values())


def parse_relations(raw: str, entities: list[dict]) -> list[RelationEdge]:
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

    entity_lookup = {
        make_entity_key(entity["name"], entity["type"]): entity
        for entity in entities
    }

    valid: list[RelationEdge] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        source = item.get("source")
        source_type = item.get("source_type")
        target = item.get("target")
        target_type = item.get("target_type")
        relation_type = item.get("relation")

        if not all(isinstance(value, str) for value in [source, source_type, target, target_type, relation_type]):
            continue

        source_type = normalize_text(source_type)
        target_type = normalize_text(target_type)
        relation_type = normalize_text(relation_type)

        if relation_type not in RELATION_TYPES:
            continue

        if source_type not in ENTITY_TYPES or target_type not in ENTITY_TYPES:
            continue

        if make_entity_key(source, source_type) not in entity_lookup:
            continue

        if make_entity_key(target, target_type) not in entity_lookup:
            continue

        if (
            normalize_text(source) == normalize_text(target)
            and source_type == target_type
        ):
            continue

        if not is_valid_relation_direction(relation_type, source_type, target_type):
            continue

        valid.append(
            {
                "source": source.strip(),
                "source_type": source_type,
                "target": target.strip(),
                "target_type": target_type,
                "relation": relation_type,
            }
        )

    return canonicalize_relations(valid[:5])


async def run_relation_extraction(text: str, entities: list[dict]) -> list[RelationEdge]:
    if len(entities) < 2:
        return []

    prompt = build_relations_prompt(text, entities)
    response = await model.ainvoke(prompt)
    content = extract_text(response)
    return parse_relations(content, entities)


async def extract_relations(state: JournalState) -> dict:
    relations = await run_relation_extraction(
        state.get("cleaned_text", state.get("raw_text", "")),
        state.get("core_entities", []),
    )
    return {"relations": relations}
