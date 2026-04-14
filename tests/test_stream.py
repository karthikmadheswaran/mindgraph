# test_stream.py
import asyncio
from app.graph import build_graph

async def test():
    workflow = build_graph()
    
    state = {
        "raw_text": "Met Arun for coffee to discuss the pitch deck. Feeling nervous about the investor meeting next friday.",
        "user_id": "e5e611e2-7618-43e2-be84-bf1fc3296382",
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
    
    async for event in workflow.astream(state):
        # event is a dict like {"node_name": {output}}
        node_name = list(event.keys())[0]
        print(f"✅ {node_name} completed")

asyncio.run(test())
