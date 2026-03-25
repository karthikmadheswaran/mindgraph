# app/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional 
from app.graph import build_graph
from app.nodes.store import supabase
from app.embeddings import get_embedding
from app.nodes.store import supabase
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.1)

app = FastAPI(title="Mindgraph Journal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://mindgraph-frontend-production.up.railway.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

workflow=build_graph()

class EntryRequest(BaseModel):
    raw_text: str
    user_id: str
    input_type: str="text"

class EntryResponse(BaseModel):
    auto_title: str
    summary: str
    classifier: list
    core_entities: list
    deadline: list

@app.get("/health")
async def health_check():
    return {"status": "alive"}

@app.post("/entries", response_model=EntryResponse)
async def create_entry(entry: EntryRequest):
    state={
        "raw_text": entry.raw_text,
        "user_id": entry.user_id,
        "input_type": entry.input_type,
        "cleaned_text": "",
        "auto_title": "",
        "summary": "",
        "classifier": [],
        "core_entities": [],
        "deadline": [],
        "trigger_check": False,
        "duplicate_of": None,
        "dedup_check_result": None
    }

    result = await workflow.ainvoke(state)


    return EntryResponse(
        auto_title=result["auto_title"],
        summary=result["summary"],
        classifier=result["classifier"],
        core_entities=result["core_entities"],
        deadline=result["deadline"]
    )

@app.get("/entries")
async def get_entries(user_id: str):
    result = supabase.table("entries")\
        .select("id, raw_text, cleaned_text, auto_title, summary, created_at") \
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .limit(20) \
        .execute()
    
    return {"entries": result.data}

@app.get("/search")
async def search_entries(query: str, user_id: str):
    # Step 1: Convert the search query into an embedding
    query_embedding = await get_embedding(query)
    
    # Step 2: Search Supabase for similar entries
    result = supabase.rpc("match_entries", {
        "query_embedding": query_embedding,
        "match_count": 5,
        "filter_user_id": user_id
    }).execute()
    
    return {"results": result.data}

def extract_text_from_response(response):
    content = response.content

    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()

@app.post("/ask")
async def ask_question(question: str, user_id: str):

    query_embedding = await get_embedding(question)

    result = supabase.rpc("match_entries", {
        "query_embedding": query_embedding,
        "match_count": 5,
        "filter_user_id": user_id
    }).execute()
    if not result.data:
        return {"answer": "No relevant entries found."}
    
    formatted_entries = []
    for i, entry in enumerate(result.data, 1):
        date = entry.get("created_at", "Unknown date")
        title = entry.get("auto_title", "No title")
        formatted_entries.append(f"Entry {i} (created at {date}, title: {title}):\n{entry['cleaned_text']}")
        
    context_text = "\n\n---\n\n".join(formatted_entries)

    # For simplicity, we'll just return the most relevant entry's cleaned_text as the "answer"
    prompt = f"""You are an assistant for a personal journal app. A user has asked the following question:
    "{question}"

    You have access to the following relevant journal entries:
    
    {context_text}
    
    Based on these journal entries, provide a helpful answer to the user's question. 
    If the journal entries do not contain relevant information, say "I don't know".
    """
    
    response = await model.ainvoke(prompt)
    answer = extract_text_from_response(response)

    return {"answer": answer}

@app.get("/deadlines")
async def get_deadlines(user_id: str):
    result = supabase.table("deadlines")\
        .select("id, description, due_date") \
        .eq("user_id", user_id)\
        .order("due_date", desc=False)\
        .execute()
    
    return {"deadlines": result.data}

@app.get("/entities")
async def get_entities(user_id: str):
    result = supabase.table("entities") \
        .select("id, name, entity_type, mention_count") \
        .eq("user_id", user_id) \
        .order("mention_count", desc=True) \
        .limit(20) \
        .execute()
    
    return {"entities": result.data}

@app.post("/entries/stream")
async def create_entry_stream(entry: EntryRequest):
    state = {
        "raw_text": entry.raw_text,
        "user_id": entry.user_id,
        "input_type": entry.input_type,
        "cleaned_text": "",
        "auto_title": "",
        "summary": "",
        "attachment_url": "",
        "classifier": [],
        "core_entities": [],
        "deadline": [],
        "trigger_check": False,
        "duplicate_of": None,
        "dedup_check_result": None,
    }

    async def event_stream():
        final_result = {}
        try:
            async for event in workflow.astream(state):
                node_name = list(event.keys())[0]
                node_output = event[node_name]
                if node_output and isinstance(node_output, dict):
                    final_result.update(node_output)
                update = {"node": node_name, "status": "completed"}
                yield f"data: {json.dumps(update)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'node': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'node': 'done', 'result': {
            'auto_title': final_result.get('auto_title', ''),
            'summary': final_result.get('summary', ''),
            'classifier': final_result.get('classifier', []),
            'core_entities': final_result.get('core_entities', []),
            'deadline': final_result.get('deadline', []),
        }})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

    









    
