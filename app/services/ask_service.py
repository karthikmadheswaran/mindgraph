import logging
from datetime import datetime, timezone

from app.ask_memory import (
    build_compaction_prompt,
    format_conversation_messages,
)
from app.db import supabase
from app.embeddings import get_embedding
from app.llm import extract_text, flash as model
from app.services.observability import langfuse_config
from app.services.reranker import rerank_entries
from app.services.timing import LatencyTrace

logger = logging.getLogger(__name__)
ASK_ROLES = ["user", "assistant"]

# --- Retrieval constants ---
VECTOR_CANDIDATE_COUNT = 15  # Phase 1.5: raised from 12 — more candidates for reranker
BM25_CANDIDATE_COUNT = 10
MAX_CONTEXT_ENTRIES = 3  # iter-1: reduced from 5 — improves precision F1 for 1-expected-entry cases
MAX_CONTEXT_ENTRIES_BROAD = 6  # Fix 2: broad queries need more context
MIN_SIMILARITY = 0.56  # iter-1: raised from 0.3 — excludes noise entries
MIN_SIMILARITY_IDENTITY = 0.50  # Fix 1: lower threshold for identity/current-state queries
MIN_RERANK_SCORE = 0.05  # Phase 2: drop reranked entries below this score

# --- Identity query detection (Fix 1) ---
_IDENTITY_PREFIXES = (
    "where do i work",
    "where do i live",
    "what do i do",
    "who do i work",
    "am i still",
    "do i still",
    "what is my job",
    "what is my role",
    "where am i working",
    "where am i based",
    "who am i",
)


def is_identity_query(question: str) -> bool:
    q = question.lower().strip()
    return any(q.startswith(p) for p in _IDENTITY_PREFIXES)


# --- Broad query detection (Fix 2) ---
_BROAD_QUERY_SIGNALS = (
    "journey",
    "history",
    "everything",
    "all about",
    "overview",
    "story of",
    "timeline",
    "progression",
    "evolution",
    "how has",
    "from the beginning",
    "summarize all",
    "tell me everything",
)


def is_broad_query(question: str) -> bool:
    q = question.lower().strip()
    return any(signal in q for signal in _BROAD_QUERY_SIGNALS)


# --- Topic switch detection ---
_TOPIC_SWITCH_PHRASES = (
    "forget about",
    "never mind",
    "ignore that",
    "let's move on",
    "changing subject",
    "different topic",
    "actually,",
)


def build_retrieval_query(question: str, history_messages: list[dict] | None = None) -> str:
    """
    Enrich embedding search with recent conversation context so follow-up
    pronouns and references have something concrete to bind to.
    """
    q_lower = question.strip().lower()
    is_topic_switch = any(q_lower.startswith(p) for p in _TOPIC_SWITCH_PHRASES)
    is_short_question = len(question.split()) < 5

    if is_topic_switch or not history_messages:
        return question.strip()

    recent_msgs = history_messages[-2:] if is_short_question else history_messages[-3:]
    recent_context = " ".join(
        str(msg.get("content", "")).strip()
        for msg in recent_msgs
        if msg.get("content")
    )

    return f"{question} {recent_context}".strip() if recent_context else question


# --- Result merging ---


def merge_results(
    vector_entries: list[dict],
    bm25_entries: list[dict],
) -> list[dict]:
    """Merge dense (vector) and sparse (BM25) results, deduplicate."""
    seen_ids: set[str] = set()
    merged: list[dict] = []

    for entry in vector_entries:
        entry_id = str(entry["id"])
        if entry_id not in seen_ids:
            seen_ids.add(entry_id)
            entry["_source"] = "vector"
            entry["_vector_sim"] = entry.get("similarity", 0) or 0
            entry["_bm25_rank"] = 0
            merged.append(entry)

    for rank, entry in enumerate(bm25_entries, 1):
        entry_id = str(entry["id"])
        if entry_id not in seen_ids:
            seen_ids.add(entry_id)
            entry["_source"] = "bm25"
            entry["_vector_sim"] = 0
            entry["_bm25_rank"] = rank
            entry["similarity"] = 0
            merged.append(entry)
        else:
            # Found by both searches — strong relevance signal
            for m in merged:
                if str(m["id"]) == entry_id:
                    m["_source"] = "both"
                    m["_bm25_rank"] = rank
                    break

    return merged


# --- Score gap filter ---


def apply_score_gap_filter(entries: list[dict]) -> list[dict]:
    """Drop reranked entries scoring much lower than the top entry."""
    if len(entries) <= 1:
        return entries
    scored = [e.get("_rerank_score") for e in entries if "_rerank_score" in e]
    if not scored:
        return entries
    top_score = max(scored)
    if top_score <= 0:
        return entries
    threshold = top_score / 3
    return [
        e for e in entries
        if "_rerank_score" not in e or e["_rerank_score"] >= threshold
    ]



# --- Repetition loop detection ---


def _word_overlap_ratio(text_a: str, text_b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def detect_repetition_loop(history_messages: list[dict]) -> bool:
    """
    Returns True if the last two assistant messages are nearly identical.
    Threshold: >60% word overlap (Jaccard similarity).
    Used to detect context window pattern dominance before LLM call.
    """
    assistant_msgs = [
        m.get("content", "")
        for m in history_messages
        if m.get("role") == "assistant"
    ]
    if len(assistant_msgs) < 2:
        return False
    overlap = _word_overlap_ratio(assistant_msgs[-1], assistant_msgs[-2])
    logger.info("Repetition loop check: overlap=%.2f (threshold=0.60)", overlap)
    return overlap > 0.60


# --- Relevance labelling ---


def get_relevance_label(similarity: float) -> str:
    if similarity >= 0.6:
        return "high"
    if similarity >= 0.45:
        return "moderate"
    return "low"


def get_relevance_label_reranked(rerank_score: float) -> str:
    if rerank_score >= 0.5:
        return "high"
    if rerank_score >= 0.2:
        return "moderate"
    return "low"


def format_retrieved_entries(entries: list[dict]) -> str:
    if not entries:
        return ""

    formatted_entries = []
    for i, entry in enumerate(entries, 1):
        date = entry.get("created_at", "Unknown date")
        title = entry.get("auto_title", "No title")

        if entry.get("relevance") == "temporal_match":
            relevance = "included (date match)"
            raw_fallback = entry.get("cleaned_text") or entry.get("raw_text") or ""
            text = entry.get("summary") or " ".join(raw_fallback.split()[:100])
        elif "_rerank_score" in entry:
            relevance = get_relevance_label_reranked(entry["_rerank_score"])
            text = entry.get("cleaned_text") or entry.get("raw_text") or ""
        elif entry.get("_keyword_match"):
            relevance = "supplementary (keyword match)"
            text = entry.get("cleaned_text") or entry.get("raw_text") or ""
        else:
            relevance = entry.get("relevance") or get_relevance_label(
                entry.get("similarity", 0) or 0
            )
            text = entry.get("cleaned_text") or entry.get("raw_text") or ""
        formatted_entries.append(
            f"Entry {i} (date: {date}, title: {title}, relevance: {relevance}):\n{text}"
        )

    return "\n\n---\n\n".join(formatted_entries)


# --- Main retrieval pipeline ---


async def retrieve_relevant_entries(
    question: str,
    user_id: str,
    history_messages: list[dict] | None = None,
    trace: LatencyTrace | None = None,
) -> list[dict]:
    """
    Two-stage hybrid retrieval:
      Stage 1: parallel dense (vector) + sparse (BM25) search
      Stage 2: merge, temporal boost, Cohere rerank
    """
    if trace is None:
        trace = LatencyTrace()

    # Determine adaptive thresholds
    min_similarity = MIN_SIMILARITY_IDENTITY if is_identity_query(question) else MIN_SIMILARITY
    max_entries = MAX_CONTEXT_ENTRIES_BROAD if is_broad_query(question) else MAX_CONTEXT_ENTRIES

    retrieval_query = build_retrieval_query(question, history_messages)

    with trace.stage("embedding"):
        query_embedding = await get_embedding(retrieval_query)

    # Stage 1: parallel dense + sparse search
    with trace.stage("vector_search"):
        vector_result = supabase.rpc(
            "match_entries",
            {
                "query_embedding": query_embedding,
                "match_count": VECTOR_CANDIDATE_COUNT,
                "filter_user_id": user_id,
            },
        ).execute()

    with trace.stage("bm25_search"):
        try:
            bm25_result = supabase.rpc(
                "search_entries_fulltext",
                {
                    "query_text": question,
                    "match_count": BM25_CANDIDATE_COUNT,
                    "filter_user_id": user_id,
                },
            ).execute()
            bm25_entries = bm25_result.data or []
        except Exception as exc:
            logger.warning("BM25 search failed, continuing with vector-only: %s", exc)
            bm25_entries = []

    # Stage 2: merge, filter, boost, rerank
    with trace.stage("merge_and_boost"):
        vector_entries = vector_result.data or []
        if vector_entries and "similarity" not in vector_entries[0]:
            logger.warning("match_entries RPC returned rows without similarity scores")

        merged = merge_results(vector_entries, bm25_entries)

        # Pre-filter using the ORIGINAL vector similarity (before any boost).
        # Temporal boost only reorders entries that already qualify — it must
        # NOT push noise entries over the threshold.
        candidates = []
        for entry in merged:
            vec_sim = entry.get("_vector_sim", 0) or 0
            source = entry.get("_source", "vector")

            if vec_sim >= min_similarity:
                candidates.append(entry)
            elif source in ("bm25", "both"):
                # BM25-found entries get a chance via reranker, but are
                # tagged so we can drop them if reranking falls back.
                entry["_bm25_only"] = True
                candidates.append(entry)

        if not candidates:
            return []

    with trace.stage("rerank"):
        if len(candidates) > max_entries:
            # Use the enriched retrieval query so the reranker has
            # conversation context for follow-up questions like "tell me more about that"
            reranked = await rerank_entries(
                query=retrieval_query,
                entries=candidates,
                top_n=max_entries,
            )
        else:
            reranked = candidates

    # Post-rerank: if reranker validated entries, trust its scores.
    # If it fell back, drop unvalidated BM25-only entries.
    final = []
    for entry in reranked:
        if "_rerank_score" in entry:
            if entry["_rerank_score"] >= MIN_RERANK_SCORE:
                final.append(entry)
            # else: reranker scored too low — noise, drop
        elif not entry.get("_bm25_only"):
            sim = entry.get("similarity", 0) or entry.get("_vector_sim", 0) or 0
            entry["relevance"] = get_relevance_label(sim)
            final.append(entry)
        # else: BM25-only without rerank validation — drop

    final = apply_score_gap_filter(final)
    return final[:max_entries]


# --- Memory compaction ---


async def compact_old_messages(user_id: str):
    """
    Background task: if user has >20 messages in ask_messages,
    compact the oldest messages (keeping the 10 most recent) into user_memory.
    Then delete the compacted messages.
    """
    try:
        count_result = (
            supabase.table("ask_messages")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .in_("role", ASK_ROLES)
            .execute()
        )
        total_count = count_result.count

        if total_count is None or total_count <= 20:
            return

        all_result = (
            supabase.table("ask_messages")
            .select("id, role, content, created_at")
            .eq("user_id", user_id)
            .in_("role", ASK_ROLES)
            .order("created_at", desc=False)
            .execute()
        )
        all_messages = all_result.data or []

        messages_to_compact = all_messages[:-10]
        if not messages_to_compact:
            return

        memory_result = (
            supabase.table("user_memory")
            .select("memory_text")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        existing_memory = ""
        if memory_result.data:
            existing_memory = memory_result.data[0].get("memory_text", "")

        conversation_text = format_conversation_messages(messages_to_compact)
        compaction_prompt = build_compaction_prompt(existing_memory, conversation_text)

        response = await model.ainvoke(
            compaction_prompt,
            config=langfuse_config(),
        )
        new_memory = extract_text(response)

        (
            supabase.table("user_memory")
            .upsert(
                {
                    "user_id": user_id,
                    "memory_text": new_memory,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="user_id",
            )
            .execute()
        )

        ids_to_delete = [msg["id"] for msg in messages_to_compact]
        if ids_to_delete:
            supabase.table("ask_messages").delete().in_("id", ids_to_delete).execute()

    except Exception as exc:
        logger.error(
            "Compact old messages failed for user %s: %s",
            user_id,
            exc,
            exc_info=True,
        )


async def get_history(user_id: str) -> dict:
    result = (
        supabase.table("ask_messages")
        .select("role, content, created_at")
        .eq("user_id", user_id)
        .in_("role", ASK_ROLES)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    messages = list(reversed(result.data)) if result.data else []
    return {"messages": messages}


async def get_memory(user_id: str) -> dict:
    result = (
        supabase.table("user_memory")
        .select("memory_text, updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"memory": None, "updated_at": None}

    row = result.data[0]
    return {
        "memory": row.get("memory_text", ""),
        "updated_at": row.get("updated_at"),
    }


async def generate_answer(
    question: str,
    user_id: str,
    exclude_message_id: str | None = None,
) -> str:
    from app.services.ask_pipeline import AskState, ask_pipeline

    trace = LatencyTrace()

    with trace.stage("conversation_fetch"):
        history_result = (
            supabase.table("ask_messages")
            .select("id, role, content")
            .eq("user_id", user_id)
            .in_("role", ASK_ROLES)
            .order("created_at", desc=True)
            .limit(11 if exclude_message_id else 10)
            .execute()
        )
        history_rows = history_result.data or []
        if exclude_message_id:
            history_rows = [
                row
                for row in history_rows
                if str(row.get("id")) != str(exclude_message_id)
            ][:10]
        history_messages = list(reversed(history_rows))
        conversation_history = format_conversation_messages(history_messages)

    with trace.stage("memory_fetch"):
        memory_result = (
            supabase.table("user_memory")
            .select("memory_text")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        user_memory = ""
        if memory_result.data:
            user_memory = memory_result.data[0].get("memory_text", "")

    if detect_repetition_loop(history_messages):
        logger.warning(
            "Repetition loop detected for user %s — pruning conversation "
            "history from prompt. Generating from memory only.",
            user_id,
        )
        conversation_history = ""

    initial_state: AskState = {
        "question": question,
        "user_id": user_id,
        "conversation_history": conversation_history,
        "long_term_memory": user_memory,
        "query_types": [],
        "time_range": None,
        "entities_mentioned": [],
        "dashboard_context_needed": False,
        "today_str": "",
        "temporal_entries": [],
        "recent_summaries": [],
        "rag_entries": [],
        "dashboard_context": {},
        "assembled_context": "",
        "answer": "",
    }

    with trace.stage("llm_generation"):
        result = await ask_pipeline.ainvoke(initial_state)

    trace.log(question)
    return result.get("answer", "")


async def new_session(user_id: str) -> dict:
    """
    Start a fresh Ask session for the user.
    Compacts all current conversation history into long-term memory, then
    deletes all ask_messages rows so the next question runs with memory only.
    """
    all_result = (
        supabase.table("ask_messages")
        .select("id, role, content, created_at")
        .eq("user_id", user_id)
        .in_("role", ASK_ROLES)
        .order("created_at", desc=False)
        .execute()
    )
    all_messages = all_result.data or []

    if all_messages:
        memory_result = (
            supabase.table("user_memory")
            .select("memory_text")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        existing_memory = ""
        if memory_result.data:
            existing_memory = memory_result.data[0].get("memory_text", "")

        conversation_text = format_conversation_messages(all_messages)
        compaction_prompt = build_compaction_prompt(existing_memory, conversation_text)
        response = await model.ainvoke(
            compaction_prompt,
            config=langfuse_config(),
        )
        new_memory = extract_text(response)

        (
            supabase.table("user_memory")
            .upsert(
                {
                    "user_id": user_id,
                    "memory_text": new_memory,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="user_id",
            )
            .execute()
        )

    supabase.table("ask_messages").delete().eq("user_id", user_id).execute()

    return {"status": "ok", "message": "Session cleared"}


async def ask(question: str, user_id: str) -> str:
    answer = await generate_answer(question, user_id)
    supabase.table("ask_messages").insert(
        [
            {
                "user_id": user_id,
                "role": "user",
                "content": question,
            },
            {
                "user_id": user_id,
                "role": "assistant",
                "content": answer,
            },
        ]
    ).execute()

    from app.services.cost_cap import record_cost

    await record_cost(user_id, "ask")
    return answer
