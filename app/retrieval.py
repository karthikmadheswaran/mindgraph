# app/retrieval.py
import json
import logging

from app.db import supabase
from app.embeddings import get_embedding
from app.llm import extract_text, flash_creative as rewrite_model

logger = logging.getLogger(__name__)


async def rewrite_query(question: str) -> list[str]:
    """Rewrite a user question into multiple search queries for better retrieval"""
    prompt = f"""You are a search query optimizer for a personal journal app.

The user asked: "{question}"

Generate 3 different search queries that would help find relevant journal entries.
Each query should approach the question from a different angle:
1. Use the original keywords/intent
2. Use synonyms and related terms  
3. Use broader context or emotional framing

Return STRICT JSON only. No explanation.
Format: ["query 1", "query 2", "query 3"]
"""
    response = await rewrite_model.ainvoke(prompt)
    content = extract_text(response)
    
    # Clean markdown fences
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    try:
        queries = json.loads(content)
        if isinstance(queries, list):
            return queries[:3]
    except json.JSONDecodeError:
        pass
    
    return [question]  # fallback to original


async def search_entries(query: str, user_id: str, match_count: int = 5) -> list[dict]:
    """Search entries using a single query"""
    embedding = await get_embedding(query)
    result = supabase.rpc("match_entries", {
        "query_embedding": embedding,
        "match_count": match_count,
        "filter_user_id": user_id,
    }).execute()
    return result.data or []


async def advanced_search(question: str, user_id: str, match_count: int = 5) -> list[dict]:
    """Advanced retrieval with query rewriting and result merging"""
    
    # Step 1: Rewrite the query into multiple search queries
    queries = await rewrite_query(question)
    logger.info("Query rewrite: %s", queries)
    
    # Step 2: Search with each query
    all_results = {}
    for query in queries:
        results = await search_entries(query, user_id, match_count=match_count)
        for entry in results:
            entry_id = entry["id"]
            if entry_id not in all_results:
                all_results[entry_id] = {
                    **entry,
                    "max_similarity": entry["similarity"],
                    "match_count": 1,
                }
            else:
                # Keep highest similarity and count matches
                all_results[entry_id]["max_similarity"] = max(
                    all_results[entry_id]["max_similarity"],
                    entry["similarity"]
                )
                all_results[entry_id]["match_count"] += 1
    
    # Step 3: Score and rank — entries found by multiple queries rank higher
    for entry in all_results.values():
        entry["combined_score"] = (
            entry["max_similarity"] * 0.7 + 
            (entry["match_count"] / len(queries)) * 0.3
        )
    
    # Step 4: Sort by combined score and return top results
    ranked = sorted(all_results.values(), key=lambda x: x["combined_score"], reverse=True)
    
    return ranked[:match_count]
