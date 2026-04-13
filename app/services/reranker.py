import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

_co = None
_last_call_time = 0.0
# In production, set to 7.0 for trial key rate limits (10/min).
# Set to 0 to disable throttling (requires a Production Cohere key).
_MIN_INTERVAL = float(os.environ.get("COHERE_MIN_INTERVAL", "7.0"))


def _get_client():
    global _co
    if _co is None:
        import cohere

        _co = cohere.Client(
            api_key=os.environ.get("COHERE_API_KEY", ""),
            timeout=2.0,
        )
    return _co


async def rerank_entries(
    query: str,
    entries: list[dict],
    top_n: int = 3,
) -> list[dict]:
    """
    Use Cohere Rerank to re-score retrieved entries by relevance to the query.
    Falls back to original order if Cohere is unavailable.
    Respects rate limits by spacing calls at least _MIN_INTERVAL seconds apart.
    """
    if not entries:
        return []

    if not os.environ.get("COHERE_API_KEY"):
        logger.warning("COHERE_API_KEY not set — skipping rerank, returning original order")
        return entries[:top_n]

    try:
        # Rate-limit: wait if needed to stay under trial key limits
        global _last_call_time
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call_time)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_time = time.monotonic()

        documents = [
            entry.get("cleaned_text") or entry.get("raw_text") or ""
            for entry in entries
        ]

        response = _get_client().rerank(
            model="rerank-v3.5",
            query=query,
            documents=documents,
            top_n=min(top_n, len(entries)),
        )

        reranked = []
        for result in response.results:
            entry = entries[result.index].copy()
            entry["_rerank_score"] = result.relevance_score
            reranked.append(entry)

        return reranked

    except Exception as exc:
        logger.error("Cohere rerank failed: %s", exc, exc_info=True)
        return entries[:top_n]
