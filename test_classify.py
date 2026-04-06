# test_classify.py

import asyncio
from app.nodes.classify import classify


# Reusable base state
base_state = {
    "raw_text": "",
    "user_id": "",
    "cleaned_text": "",
    "auto_title": "",
    "summary": "",
    "input_type": "text",
    "attachment_url": "",
    "classifier": [],
    "core_entities": [],
    "deadline": [],
    "relations": [],
    "trigger_check": False,
    "duplicate_of": None,
    "dedup_check_result": None,
}


async def run_test(state):
    result = await classify(state)
    print("INPUT :", state["raw_text"])
    print("OUTPUT:", result["classifier"])
    print("-" * 50)


async def test():
    # -----------------------------------
    # Test Case 1
    # -----------------------------------
    state1 = {
        **base_state,
        "raw_text": "Had a meeting with Rahul about ProjectX",
    }

    # Expected Output:
    # ["work"] 
    # (Meeting + Project reference → work-related classification)

    await run_test(state1)


    # -----------------------------------
    # Test Case 2
    # -----------------------------------
    state2 = {
        **base_state,
        "raw_text": "My headache won't go away, couldn't focus on the quarterly report",
    }

    # Expected Output:
    # ["health", "work"]
    # (Headache → health, quarterly report → work)


    await run_test(state2)


    # -----------------------------------
    # Test Case 3
    # -----------------------------------
    state3 = {
        **base_state,
        "raw_text": "Took mom to the hospital, spent 5000 on tests",
    }

    # Expected Output:
    # ["family", "health", "finance"]
    # (mom → family, hospital/tests → health, spent money → finance)


    await run_test(state3)


asyncio.run(test())
