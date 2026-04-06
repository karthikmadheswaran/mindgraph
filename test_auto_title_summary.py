# test_classify.py

import asyncio
from app.nodes.title_summary import title_summary



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
    result = await title_summary(state)
    print("INPUT :", state["raw_text"])
    print("TITLE:", result["auto_title"])
    print("SUMMARY:", result["summary"])
    print("-" * 50)


async def test():
    # -----------------------------------
    # Test Case 1
    # -----------------------------------
    state1 = {
        **base_state,
        "raw_text": "Today was exhausting. I had back-to-back meetings and thought I wouldn't finish the dashboard. By 8 PM I finally fixed the filtering bug and sent it to my manager. I feel relieved but drained.",
    }

    '''{
  "auto_title": "Dashboard Fix Relief ✅",
  "summary": "A long day of meetings and pressure ended with me fixing the dashboard filtering bug and sending it to my manager. I felt relieved, but completely drained."
}'''

    await run_test(state1)


    # -----------------------------------
    # Test Case 2
    # -----------------------------------
    state2 = {
        **base_state,
        "raw_text": "I argued with my mom today and it stayed in my head all evening. I know I was harsh. I want to call her tomorrow and talk calmly.",
    }

    '''{
  "auto_title": "After the Argument 💭",
  "summary": "I kept thinking about an argument with my mom and felt bad about how I spoke. I want to call her tomorrow and have a calmer conversation."
}'''


    await run_test(state2)


    # -----------------------------------
    # Test Case 3
    # -----------------------------------
    state3 = {
        **base_state,
        "raw_text": "Bad day. Didn't do much. Just tired.",
    }

    '''{
  "auto_title": "Tired Day 😴",
  "summary": "Had a rough day with no major accomplishments. I felt tired and unmotivated."
}'''


    await run_test(state3)


asyncio.run(test())
