# rag_evaluation.py
"""
RAG Evaluation for MindGraph Journal App

Measures three things:
1. Retrieval Accuracy - Did we find the right entries?
2. Answer Quality - Did the LLM answer correctly without hallucinating?
3. Latency - How fast is retrieval + generation?

Usage: python rag_evaluation.py
"""

import asyncio
import time
import json
import os
from dotenv import load_dotenv
from app.embeddings import get_embedding
from app.nodes.store import supabase
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.1)

USER_ID = "e5e611e2-7618-43e2-be84-bf1fc3296382"

# ─── TEST DATASET ───
# Each test case has:
#   question: what the user asks
#   expected_titles: entry titles that SHOULD be retrieved (top results)
#   expected_keywords: words that MUST appear in the answer
#   forbidden_keywords: words that should NOT appear (hallucination check)

TEST_CASES = [
    {
        "question": "What have I been working on with Sneha?",
        "expected_titles": ["Debugging and Startup Ideas", "Debugging Success and Feeling Homesick", "Had coffee with Sneha"],
        "expected_keywords": ["auth", "debug", "Sneha"],
        "forbidden_keywords": [],
    },
    {
        "question": "What are my health issues recently?",
        "expected_titles": ["Struggling Through a Migraine Day", "Cosmic Perspective and Life Logistics"],
        "expected_keywords": ["migraine", "medicine"],
        "forbidden_keywords": [],
    },
    {
        "question": "Tell me about my family and parents",
        "expected_titles": ["Planning Parents' Bangalore Visit", "Upcoming Deadlines and Family Calls"],
        "expected_keywords": ["mom", "dad", "Bangalore"],
        "forbidden_keywords": [],
    },
    {
        "question": "What startup ideas have I discussed?",
        "expected_titles": ["Startup Strategy with Arun", "Debugging and Startup Ideas"],
        "expected_keywords": ["Arun", "startup"],
        "forbidden_keywords": [],
    },
    {
        "question": "How much money have I been spending?",
        "expected_titles": ["Productive Day Amidst Financial Stress", "Struggling Through a Migraine Day", "Cosmic Perspective and Life Logistics", "Amazing Brigade Road Coffee Discovery"],
        "expected_keywords": ["spent", "medicine"],
        "forbidden_keywords": [],
    },
    {
        "question": "What happened when I quit my job?",
        "expected_titles": ["Quitting Job for New Ventures"],
        "expected_keywords": ["quit", "exciting", "scary"],
        "forbidden_keywords": [],
    },
    {
        "question": "What places have I visited in Bangalore?",
        "expected_titles": ["Debugging Success and Feeling Homesick", "Amazing Brigade Road Coffee Discovery", "Cosmic Perspective and Life Logistics"],
        "expected_keywords": ["Bangalore"],
        "forbidden_keywords": [],
    },
    {
        "question": "What bugs have I been fixing?",
        "expected_titles": ["Addressing Auth Module Issues", "Fixing Session Timeout Bug", "Debugging Success and Feeling Homesick"],
        "expected_keywords": ["auth", "bug"],
        "forbidden_keywords": [],
    },
    {
        "question": "How has my mood been lately?",
        "expected_titles": ["Quitting Job for New Ventures", "Struggling Through a Migraine Day", "Debugging Success and Feeling Homesick"],
        "expected_keywords": [],
        "forbidden_keywords": [],
    },
    {
        "question": "What deadlines do I have coming up?",
        "expected_titles": ["Upcoming Deadlines and Family Calls", "Pitch Deck Prep and Nerves"],
        "expected_keywords": [],
        "forbidden_keywords": [],
    },
    {
        "question": "Who is Arun and what have we discussed?",
        "expected_titles": ["Startup Strategy with Arun"],
        "expected_keywords": ["Arun", "startup"],
        "forbidden_keywords": [],
    },
    {
        "question": "What did I do about the MindGraph deployment?",
        "expected_titles": ["MindGraph Deployment Success in Bangalore", "Deployment Progress and Security Lessons"],
        "expected_keywords": ["deploy", "Railway"],
        "forbidden_keywords": [],
    },
    {
        "question": "Have I been exercising recently?",
        "expected_titles": ["Debugging Success and Feeling Homesick", "Cosmic Perspective and Life Logistics"],
        "expected_keywords": ["run", "gym"],
        "forbidden_keywords": [],
    },
    {
        "question": "What coffee experiences have I had?",
        "expected_titles": ["Amazing Brigade Road Coffee Discovery", "Debugging and Startup Ideas", "Had coffee with Sneha"],
        "expected_keywords": ["coffee"],
        "forbidden_keywords": [],
    },
    {
        "question": "What have I been feeling homesick about?",
        "expected_titles": ["Debugging Success and Feeling Homesick"],
        "expected_keywords": ["home", "missing"],
        "forbidden_keywords": [],
    },
]


def extract_text_from_response(response):
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block["text"] if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()


async def evaluate_retrieval(question: str, expected_titles: list[str]) -> dict:
    """Evaluate if the right entries are retrieved"""
    start = time.time()
    
    query_embedding = await get_embedding(question)
    
    result = supabase.rpc("match_entries", {
        "query_embedding": query_embedding,
        "match_count": 5,
        "filter_user_id": USER_ID
    }).execute()
    
    retrieval_time = time.time() - start
    
    retrieved_titles = [r.get("auto_title", "") for r in result.data]
    
    # Calculate retrieval accuracy
    # How many expected titles appear in top 5 results?
    hits = 0
    for expected in expected_titles:
        for retrieved in retrieved_titles:
            if expected.lower() in retrieved.lower() or retrieved.lower() in expected.lower():
                hits += 1
                break
    
    precision = hits / len(retrieved_titles) if retrieved_titles else 0
    recall = hits / len(expected_titles) if expected_titles else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        "retrieved_titles": retrieved_titles,
        "expected_titles": expected_titles,
        "hits": hits,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "retrieval_time_ms": round(retrieval_time * 1000),
        "similarities": [round(r.get("similarity", 0), 3) for r in result.data],
    }


async def evaluate_answer(question: str, retrieved_entries: list, expected_keywords: list[str], forbidden_keywords: list[str]) -> dict:
    """Evaluate the quality of the generated answer"""
    start = time.time()
    
    formatted_entries = []
    for i, entry in enumerate(retrieved_entries, 1):
        date = entry.get("created_at", "Unknown")
        title = entry.get("auto_title", "Untitled")
        formatted_entries.append(f"Entry {i} ({date}, {title}):\n{entry['cleaned_text']}")
    
    context = "\n\n---\n\n".join(formatted_entries)
    
    prompt = f"""You are an assistant for a personal journal app. A user has asked:
    "{question}"

    Relevant journal entries:
    {context}
    
    Based on these entries, provide a helpful answer. If the entries don't contain relevant info, say "I don't know"."""
    
    response = await model.ainvoke(prompt)
    answer = extract_text_from_response(response)
    
    generation_time = time.time() - start
    
    # Check expected keywords
    answer_lower = answer.lower()
    keywords_found = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    keywords_missing = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
    
    # Check forbidden keywords (hallucination)
    hallucinations = [kw for kw in forbidden_keywords if kw.lower() in answer_lower]
    
    keyword_score = len(keywords_found) / len(expected_keywords) if expected_keywords else 1.0
    hallucination_score = 1.0 - (len(hallucinations) / len(forbidden_keywords)) if forbidden_keywords else 1.0
    
    return {
        "answer": answer[:200] + "..." if len(answer) > 200 else answer,
        "keywords_found": keywords_found,
        "keywords_missing": keywords_missing,
        "hallucinations": hallucinations,
        "keyword_score": round(keyword_score, 3),
        "hallucination_score": round(hallucination_score, 3),
        "generation_time_ms": round(generation_time * 1000),
    }


async def run_evaluation():
    """Run full RAG evaluation"""
    print("=" * 70)
    print("🧪 MindGraph RAG Evaluation")
    print("=" * 70)
    print(f"Test cases: {len(TEST_CASES)}")
    print()
    
    results = []
    total_retrieval_time = 0
    total_generation_time = 0
    total_f1 = 0
    total_keyword_score = 0
    total_hallucination_score = 0
    
    for i, test in enumerate(TEST_CASES, 1):
        print(f"─── Test {i}/{len(TEST_CASES)}: {test['question']}")
        
        # Step 1: Evaluate retrieval
        retrieval = await evaluate_retrieval(test["question"], test["expected_titles"])
        
        # Step 2: Get entries for answer generation
        query_embedding = await get_embedding(test["question"])
        entries_result = supabase.rpc("match_entries", {
            "query_embedding": query_embedding,
            "match_count": 5,
            "filter_user_id": USER_ID
        }).execute()
        
        # Step 3: Evaluate answer
        answer_eval = await evaluate_answer(
            test["question"],
            entries_result.data,
            test["expected_keywords"],
            test["forbidden_keywords"]
        )
        
        # Print results
        print(f"  Retrieval: F1={retrieval['f1_score']} | Precision={retrieval['precision']} | Recall={retrieval['recall']} | {retrieval['retrieval_time_ms']}ms")
        print(f"  Retrieved: {[t[:30] for t in retrieval['retrieved_titles']]}")
        print(f"  Answer:    Keywords={answer_eval['keyword_score']} | Hallucination={answer_eval['hallucination_score']} | {answer_eval['generation_time_ms']}ms")
        if answer_eval["keywords_missing"]:
            print(f"  ⚠ Missing:  {answer_eval['keywords_missing']}")
        if answer_eval["hallucinations"]:
            print(f"  ❌ Hallucinated: {answer_eval['hallucinations']}")
        print()
        
        # Accumulate totals
        total_retrieval_time += retrieval["retrieval_time_ms"]
        total_generation_time += answer_eval["generation_time_ms"]
        total_f1 += retrieval["f1_score"]
        total_keyword_score += answer_eval["keyword_score"]
        total_hallucination_score += answer_eval["hallucination_score"]
        
        results.append({
            "question": test["question"],
            "retrieval": retrieval,
            "answer": answer_eval,
        })
    
    # Summary
    n = len(TEST_CASES)
    print("=" * 70)
    print("📊 EVALUATION SUMMARY")
    print("=" * 70)
    print(f"  Total test cases:         {n}")
    print(f"  Avg Retrieval F1:         {round(total_f1 / n, 3)}")
    print(f"  Avg Keyword Score:        {round(total_keyword_score / n, 3)}")
    print(f"  Avg Hallucination Score:  {round(total_hallucination_score / n, 3)}")
    print(f"  Avg Retrieval Latency:    {round(total_retrieval_time / n)}ms")
    print(f"  Avg Generation Latency:   {round(total_generation_time / n)}ms")
    print(f"  Total Evaluation Time:    {round((total_retrieval_time + total_generation_time) / 1000, 1)}s")
    print("=" * 70)
    
    # Save results to JSON
    with open("rag_evaluation_results.json", "w") as f:
        json.dump({
            "summary": {
                "test_cases": n,
                "avg_retrieval_f1": round(total_f1 / n, 3),
                "avg_keyword_score": round(total_keyword_score / n, 3),
                "avg_hallucination_score": round(total_hallucination_score / n, 3),
                "avg_retrieval_latency_ms": round(total_retrieval_time / n),
                "avg_generation_latency_ms": round(total_generation_time / n),
            },
            "results": results,
        }, f, indent=2, default=str)
    
    print("\n📁 Detailed results saved to rag_evaluation_results.json")


if __name__ == "__main__":
    asyncio.run(run_evaluation())