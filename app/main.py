# app/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional 
from app.graph import build_graph
from fastapi import FastAPI, BackgroundTasks
from app.nodes.store import supabase
from app.embeddings import get_embedding
from app.nodes.store import supabase
from app.retrieval import advanced_search
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
load_dotenv()
Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.1)

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
    langfuse_handler = LangfuseCallbackHandler()
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

    result = await workflow.ainvoke(state, config={"callbacks": [langfuse_handler]})


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
        .select("id, raw_text, cleaned_text, auto_title, summary, created_at, status, pipeline_stage") \
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
    langfuse_handler = LangfuseCallbackHandler()
    
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

    prompt = f"""You are an assistant for a personal journal app. A user has asked the following question:
    "{question}"

    You have access to the following relevant journal entries:
    {context_text}
    
    Based on these journal entries, provide a helpful answer to the user's question. 
    If the journal entries do not contain relevant information, say "I don't know".
    """
    
    response = await model.ainvoke(prompt, config={"callbacks": [langfuse_handler]})
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
    langfuse_handler = LangfuseCallbackHandler()
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
            async for event in workflow.astream(state, config={"callbacks": [langfuse_handler]}):
                node_name = list(event.keys())[0]
                node_output = event[node_name]
                if node_output and isinstance(node_output, dict):
                    final_result.update(node_output)
                update = {"node": node_name, "status": "completed"}
                yield f"data: {json.dumps(update)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'node': 'error', 'message': str(e)})}\n\n"

        # Convert deadlines to serializable format
        deadlines = final_result.get('deadline', [])
        serializable_deadlines = []
        for d in deadlines:
            serializable_deadlines.append({
                "description": d.get("description", ""),
                "due_at": str(d.get("due_at", "")),
                "raw_text": d.get("raw_text", ""),
            })

        yield f"data: {json.dumps({'node': 'done', 'result': {
            'auto_title': final_result.get('auto_title', ''),
            'summary': final_result.get('summary', ''),
            'classifier': final_result.get('classifier', []),
            'core_entities': final_result.get('core_entities', []),
            'deadline': serializable_deadlines,
        }})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.post("/entries/async")
async def create_entry_async(entry: EntryRequest, background_tasks: BackgroundTasks):
    # Insert skeleton row immediately so it appears on dashboard
    skeleton = supabase.table("entries").insert({
        "raw_text": entry.raw_text,
        "user_id": entry.user_id,
        "cleaned_text": "",
        "auto_title": "",
        "summary": "",
        "status": "processing",
        "pipeline_stage": "normalize",
    }).execute()

    entry_id = skeleton.data[0]["id"] if skeleton.data else None

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
        "entry_id": str(entry_id) if entry_id else None,
    }

    async def process_entry():
        try:
            langfuse_handler = LangfuseCallbackHandler()
            async for event in workflow.astream(state, config={"callbacks": [langfuse_handler]}):
                node_name = list(event.keys())[0]
                if entry_id:
                    supabase.table("entries").update({
                        "pipeline_stage": node_name
                    }).eq("id", entry_id).execute()
        except Exception as e:
            print(f"❌ Background processing error: {e}")
            if entry_id:
                supabase.table("entries").update({
                    "status": "error",
                    "pipeline_stage": None
                }).eq("id", entry_id).execute()

    background_tasks.add_task(process_entry)

    return {"status": "processing", "entry_id": entry_id, "message": "Your entry is being processed. Check the dashboard in a few seconds."}

@app.get("/entries/{entry_id}/status")
async def get_entry_status(entry_id: str):
    result = supabase.table("entries") \
        .select("id, status, pipeline_stage") \
        .eq("id", entry_id) \
        .single() \
        .execute()
    return result.data

@app.get("/search")
async def search_entries_endpoint(query: str, user_id: str):
    results = await advanced_search(query, user_id, match_count=5)
    return {"results": results}
    









    
