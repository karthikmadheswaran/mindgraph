import logging
import re
from datetime import datetime, timezone, timedelta

from app.ask_memory import (
    build_ask_prompt,
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


# --- Temporal recency boost ---
_TEMPORAL_SIGNALS = (
    "today",
    "this week",
    "this month",
    "recently",
    "lately",
    "last few days",
    "past week",
    "current",
    "right now",
    "what have i been",
    "what am i",
)


def has_temporal_signal(question: str) -> bool:
    q = question.lower()
    return any(signal in q for signal in _TEMPORAL_SIGNALS)


# --- Temporal query classification (for routing) ---

# Pure temporal summary phrases — these bypass the content-word check entirely.
# They are unambiguously asking for a time-period overview, not a topical filter.
_PURE_TEMPORAL_PATTERNS = [
    r"\bwhat did i do (?:today|this week|yesterday|recently|this morning|this evening)\b",
    r"\bwhat happened (?:today|this week|yesterday|last week|this month)\b",
    r"\bgive me .{0,30}(?:my|this) week\b",
    r"\bgive me my (?:today|week|month)\b",
    r"\bweekly summary\b",
    r"\bany updates (?:today|this week|recently)\b",
    r"\brecent entries\b",
    r"\b(?:summarize|summary of) (?:my )?(?:today|this week|last week|this month|the week)\b",
    r"\bwhat (?:did i write|have i written) (?:today|yesterday|this week|recently)\b",
]

# Each tuple: (regex, days_back, is_yesterday_special_case)
_TEMPORAL_WINDOW_PATTERNS = [
    (r"\btoday\b|\bthis morning\b|\bthis evening\b", 1, False),
    (r"\byesterday\b", 2, True),
    (r"\bthis week\b|\bpast week\b|\blast 7 days\b|\blast week\b", 7, False),
    (r"\bweekly\b|\bweek\b", 7, False),
    (r"\bthis month\b|\bpast month\b|\blast 30 days\b", 30, False),
    (r"\brecently\b|\brecent\b", 7, False),
]

# Function/filler words that don't constitute a topical filter
_CONTENT_WORD_FILLERS = {
    "i", "me", "my", "you", "your", "we", "our", "it", "its",
    "the", "a", "an",
    "is", "are", "was", "were", "be", "been", "am",
    "do", "did", "does", "have", "has", "had",
    "give", "tell", "show", "get", "find", "see", "know", "think",
    "what", "when", "where", "who", "how", "which",
    "this", "that", "these", "those", "here", "there",
    "for", "of", "to", "and", "or", "but", "in", "on", "at", "about",
    "with", "by", "from", "into", "any", "some",
    "something", "anything", "everything", "nothing",
    "factual", "recent", "new", "latest", "general", "overview",
}

# Temporal phrases to strip before counting content words
_TEMPORAL_CLEANUP_PATTERNS = [
    r"\blast\s+\d+\s+days?\b",
    r"\btoday\b", r"\bthis morning\b", r"\bthis evening\b",
    r"\byesterday\b",
    r"\bthis week\b", r"\bpast week\b", r"\blast 7 days\b", r"\blast week\b",
    r"\bthis month\b", r"\bpast month\b", r"\blast 30 days\b",
    r"\brecently\b", r"\brecent\b", r"\bweekly\b",
]


def classify_temporal_query(question: str) -> dict | None:
    """
    Detect pure temporal queries (asking for a time-period summary) and return
    {"start_date": datetime, "end_date": datetime} if so, else None.

    Mixed queries like "what have I been stressed about this week?" are routed to
    the normal retrieval pipeline (return None).
    """
    q = question.lower().strip().rstrip("?.,!")
    now = datetime.now(timezone.utc)

    # Phase 1: "last N days" explicit pattern
    m = re.search(r"\blast\s+(\d+)\s+days?\b", q)
    custom_days = int(m.group(1)) if m else None

    # Phase 2: Detect temporal window from keywords
    days_back = custom_days
    is_yesterday = False
    if days_back is None:
        for pattern, days, yesterday_flag in _TEMPORAL_WINDOW_PATTERNS:
            if re.search(pattern, q):
                days_back = days
                is_yesterday = yesterday_flag
                break

    if days_back is None:
        return None  # No temporal signal — normal pipeline

    # Phase 3: Pure temporal phrase check — short-circuit content-word analysis
    is_pure = any(re.search(p, q) for p in _PURE_TEMPORAL_PATTERNS)

    if not is_pure:
        # Phase 4: Strip temporal phrases, count remaining content words.
        # Any meaningful topical word → mixed query → normal pipeline.
        stripped = q
        for pattern in _TEMPORAL_CLEANUP_PATTERNS:
            stripped = re.sub(pattern, "", stripped)

        content_words = [
            w for w in re.split(r"\W+", stripped)
            if w and w not in _CONTENT_WORD_FILLERS
        ]
        if content_words:
            return None  # Topical+temporal → normal pipeline

    end_date = now
    if is_yesterday:
        # "yesterday" → 24–48 hours ago
        end_date = now - timedelta(hours=24)
        start_date = now - timedelta(hours=48)
    else:
        start_date = now - timedelta(days=days_back)

    return {"start_date": start_date, "end_date": end_date}


def fetch_entries_by_date_range(
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    max_summary_tokens: int = 3000,
) -> list[dict]:
    """
    Fetch completed journal entries within a date range directly from the DB.
    Bypasses embedding, vector search, and reranking entirely.

    Uses summary fields (~50 tokens each) instead of raw text so far more
    entries fit within the token budget. Entries are ordered most-recent-first;
    accumulation stops when the next entry would exceed max_summary_tokens.
    """
    result = (
        supabase.table("entries")
        .select("id, auto_title, summary, created_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .is_("deleted_at", "null")
        .gte("created_at", start_date.isoformat())
        .lte("created_at", end_date.isoformat())
        .order("created_at", desc=True)
        .execute()
    )
    all_entries = result.data or []

    included: list[dict] = []
    token_count = 0
    for entry in all_entries:
        text = entry.get("summary") or ""
        entry_tokens = len(text.split()) * 1.3
        if token_count + entry_tokens > max_summary_tokens:
            break
        entry["relevance"] = "temporal_match"
        included.append(entry)
        token_count += entry_tokens

    if len(all_entries) > len(included):
        logger.warning(
            "Temporal fetch truncated: %d/%d entries included (token cap %d)",
            len(included),
            len(all_entries),
            max_summary_tokens,
        )

    return included


def apply_temporal_boost(entries: list[dict], question: str) -> list[dict]:
    """Boost recent entries' similarity scores. Decays over 7 days."""
    now = datetime.now(timezone.utc)
    boost_factor = 0.12 if has_temporal_signal(question) else 0.08

    for entry in entries:
        created_at_str = entry.get("created_at", "")
        try:
            if isinstance(created_at_str, str):
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            else:
                created_at = created_at_str

            days_ago = (now - created_at).days
            if days_ago <= 7:
                boost = boost_factor * (1 - days_ago / 8)
                entry["_recency_boost"] = round(boost, 4)
                vec_sim = entry.get("_vector_sim", 0) or entry.get("similarity", 0) or 0
                if vec_sim > 0:
                    entry["similarity"] = vec_sim + boost
            else:
                entry["_recency_boost"] = 0
        except (ValueError, TypeError):
            entry["_recency_boost"] = 0

    return entries


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

        # Apply temporal boost for ranking (not threshold filtering)
        candidates = apply_temporal_boost(candidates, question)

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

    temporal_range = classify_temporal_query(question)
    logger.info(
        "Ask routing: %s (question: %s)",
        "temporal" if temporal_range else "topical",
        question[:80],
    )

    if temporal_range:
        with trace.stage("temporal_fetch"):
            relevant_entries = fetch_entries_by_date_range(
                user_id=user_id,
                start_date=temporal_range["start_date"],
                end_date=temporal_range["end_date"],
            )
    else:
        relevant_entries = await retrieve_relevant_entries(
            question,
            user_id,
            history_messages=history_messages,
            trace=trace,
        )
    context_text = format_retrieved_entries(relevant_entries)

    with trace.stage("prompt_build"):
        prompt = build_ask_prompt(
            question=question,
            user_memory=user_memory,
            conversation_history=conversation_history,
            context_text=context_text,
        )

    with trace.stage("llm_generation"):
        response = await model.ainvoke(prompt, config=langfuse_config())

    trace.log(question)
    return extract_text(response)


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

    return answer
