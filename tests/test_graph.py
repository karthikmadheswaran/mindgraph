import asyncio
from app.graph import build_graph

async def test():
    workflow = build_graph()
    
    state = {
        "raw_text": "Finally quit my job today. Scary but exciting. Need to update my resume by next monday and reach out to Arun about the startup idea. Spent the evening celebrating with Deepa at that new cafe in Koramangala. Feeling anxious about money though.",
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
    
    result = await workflow.ainvoke(state)
    
    print("=" * 60)
    print("📝 RAW INPUT:")
    print(result["raw_text"])
    print("=" * 60)
    print("🧹 CLEANED TEXT:")
    print(result["cleaned_text"])
    print("=" * 60)
    print("📌 TITLE:", result["auto_title"])
    print("📋 SUMMARY:", result["summary"])
    print("=" * 60)
    print("🏷️  CATEGORIES:", result["classifier"])
    print("👤 ENTITIES:", result["core_entities"])
    print("⏰ DEADLINES:", result["deadline"])
    print("=" * 60)
    print("💾 STORED: Check debug prints above for details")
    

asyncio.run(test())
