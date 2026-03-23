# test_deadline.py

import asyncio
from app.nodes.deadline import extract_deadlines




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
    "trigger_check": False,
    "duplicate_of": None,
    "dedup_check_result": None,
}


async def run_test(state):
    result = await extract_deadlines(state)
    print("raw text:", state["raw_text"])
    print("CLEANED TEXT:", state["cleaned_text"])
    print("DEADLINES:", result["deadline"])
    print("-" * 50)


async def test():
    # -----------------------------------
    # Test Case 1
    # -----------------------------------
    state1 = {
        **base_state,
        "raw_text": "gonna meet rahul tmrw about ProjectX, my back hurts spent 2000 on meds",
        "cleaned_text": "I am going to meet Rahul 2026-02-26 about ProjectX. My back hurts; I spent 2000 on medications.",
    }


    await run_test(state1)


    # -----------------------------------
    # Test Case 2
    # -----------------------------------
    state2 = {
        **base_state,
        "raw_text": "submit visa docs by friday, pay rent on 1st march, call mom next monday",
        "cleaned_text": "Submit visa documents by 2026-02-27, pay rent on 2026-03-01, call mom on 2026-03-02.",
    }

    


    await run_test(state2)


    # -----------------------------------
    # Test Case 3
    # -----------------------------------
    state3 = {
        **base_state,
        "raw_text": "felt tired all day, argued with my manager, need to sleep early",
        "cleaned_text": "I felt tired all day, argued with my manager, and need to sleep early.",
    }

    '''{
  "auto_title": "Tired Day 😴",
  "summary": "Had a rough day with no major accomplishments. I felt tired and unmotivated."
}'''


    await run_test(state3)


asyncio.run(test())