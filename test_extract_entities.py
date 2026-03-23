# test_normalize.py
import asyncio
from app.nodes.normalize import normalize
from app.nodes.extract_entities import extract_entities

async def test():
    # Test case 1: dates + typos + slang
    state = {
        "raw_text": "Had a meeting with Rahul and Priya at Google office about ProjectX using Figma",
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
    
    result = await extract_entities(state)
    print("INPUT:", state["raw_text"])      
    print("OUTPUT:", result["core_entities"])

    #expected output: [
    #  {"name": "Rahul", "type": "person"},
    #  {"name": "Priya", "type": "person"},
    #  {"name": "Google", "type": "organization"},
    #  {"name": "ProjectX", "type": "project"},
    #  {"name": "Figma", "type": "tool"}
    #]
    
asyncio.run(test())