# test_store_node.py
# Run this to test your store.py pipeline end-to-end with the same user_id

import asyncio
from datetime import datetime

from app.nodes.store import (
    store_entry,
    store_entry_tags,
    store_entities,
    store_entry_deadlines,
    store_entry_entities,
    store_node,
)

USER_ID = "e5e611e2-7618-43e2-be84-bf1fc3296382"

# Reusable sample state (matches your JournalState shape)
test_state = {
    "user_id": USER_ID,
    "raw_text": (
        "Had a terrible headache all day but still managed to finish the API docs for ProjectX. "
        "Need to submit the PR by friday. Met with Priya and Rahul at the Google office to discuss the roadmap. "
        "Spent 3000 on medicines. Gonna call mom tomorrow to check on her knee surgery recovery."
    ),
    "cleaned_text": (
        "Had a terrible headache all day but still managed to finish the API documentation for ProjectX. "
        "Need to submit the PR by 2026-02-27. Met with Priya and Rahul at the Google office to discuss the roadmap. "
        "Spent 3,000 on medicines. Going to call Mom on 2026-02-26 to check on her knee surgery recovery."
    ),
    "auto_title": "Productive Work Despite Persistent Headache 🤕",
    "summary": (
        "Despite a terrible headache, I completed the ProjectX API documentation, met colleagues to discuss the roadmap, "
        "and planned a call to check on my mother's surgery recovery."
    ),
    "input_type": "text",
    "attachment_url": "",
    "classifier": ["work", "health", "finance", "family"],
    "core_entities": [
        {"name": "ProjectX", "type": "project"},
        {"name": "API documentation", "type": "task"},
        {"name": "PR", "type": "task"},
        {"name": "Priya", "type": "person"},
        {"name": "Rahul", "type": "person"},
        {"name": "Google", "type": "organization"},
        {"name": "Google office", "type": "place"},
        {"name": "Mom", "type": "person"},
        {"name": "knee surgery", "type": "event"},
        {"name": "call Mom", "type": "task"},
    ],
    "deadline": [
        {
            "description": "Submit the PR",
            "due_at": datetime(2026, 2, 27, 0, 0),
            "raw_text": "friday",
        },
        {
            "description": "Call mom",
            "due_at": datetime(2026, 2, 26, 0, 0),
            "raw_text": "tomorrow",
        },
    ],
    "trigger_check": False,
    "duplicate_of": None,
    "dedup_check_result": None,
}


async def test_store_entry_only():
    print("\n=== TEST: store_entry ===")
    result = await store_entry(test_state)
    print("store_entry result:", result)
    return result.get("id")


async def test_store_helpers(entry_id: int):
    print("\n=== TEST: helper functions ===")

    tags_result = await store_entry_tags(entry_id, test_state["classifier"])
    print("store_entry_tags:", tags_result)

    entity_ids = await store_entities(
        test_state["core_entities"],
        test_state["user_id"],
        test_state["summary"],
    )
    print("store_entities IDs:", entity_ids)

    link_result = await store_entry_entities(entry_id, entity_ids)
    print("store_entry_entities:", link_result)

    deadlines_result = await store_entry_deadlines(
        entry_id,
        test_state["deadline"],
        test_state["user_id"],
    )
    print("store_entry_deadlines:", deadlines_result)

    return {
        "tags_result": tags_result,
        "entity_ids": entity_ids,
        "link_result": link_result,
        "deadlines_result": deadlines_result,
    }


async def test_store_node_end_to_end():
    print("\n=== TEST: store_node (end-to-end) ===")
    result = await store_node(test_state)
    print("store_node result:", result)
    return result


async def main():
    # 1) Optional granular tests
    entry_id = await test_store_entry_only()
    if entry_id:
        await test_store_helpers(entry_id)

    # 2) End-to-end test (inserts a second entry; expected)
    await test_store_node_end_to_end()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())