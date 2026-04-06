# test_normalize.py
import asyncio
from app.nodes.normalize import normalize

async def test():
    tests = [
        "Need to submit report by next monday and call mom tomorrow",
        "Meeting with Rahul by friday",
        "Finish the deck by this wednesday",
        "Started the project last tuesday",
        "Doctor appointment in 3 days",
        "gonna meet rahul tmrw about ProjectX, my back hurts spent 2000 on meds",
    ]
    
    for t in tests:
        state = {
            "raw_text": t,
            "cleaned_text": "",
            "user_id": "", "auto_title": "", "summary": "",
            "input_type": "text", "attachment_url": "",
            "classifier": [], "core_entities": [], "deadline": [], "relations": [],
            "trigger_check": False, "duplicate_of": None,
            "dedup_check_result": None,
        }
        result = await normalize(state)
        print(f"INPUT:  {t}")
        print(f"OUTPUT: {result['cleaned_text']}")
        print("---")

asyncio.run(test())
