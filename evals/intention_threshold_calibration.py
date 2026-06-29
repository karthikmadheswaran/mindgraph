"""Calibrate INTENTION_MATCH_THRESHOLD (drift P2 resolution).

Resolution (app/intention_resolver.resolve_and_persist_intentions) treats a new
candidate intention as a RE-REFERENCE of an existing one when their embedding
cosine >= INTENTION_MATCH_THRESHOLD, otherwise INSERTS a new intention.

The failure asymmetry sets the bias. A false MERGE silently destroys a real
intention — it folds into another row, invisible and unrecoverable from the
user's view. A false SPLIT only creates a visible duplicate card the user can
dismiss. So tune CONSERVATIVE: pick a threshold ABOVE the observed
distinct-intention max so ZERO distinct pairs merge, even at the cost of some
true restatements splitting (same reasoning as the entry-dedup 0.92 bias and the
entity-resolution caution).

This embeds SYNTHETIC fixtures (no private data — safe to commit results) with
the SAME task_type the resolver uses (RETRIEVAL_DOCUMENT), sweeps thresholds, and
reports false-merge / false-split counts per threshold. The hard property: at the
chosen threshold, false_merges == 0.

Run (Vertex locally; the AI Studio key is depleted):
    USE_VERTEX=1 SAVE_RESULTS=1 python -m evals.intention_threshold_calibration
"""
import asyncio
import math
import os
import random

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"), encoding="utf-8-sig")

from app.embeddings import get_embedding
from evals.provenance import save_results

# (a, b) restatements of the SAME intention -> SHOULD merge.
SHOULD_MERGE = [
    ("want to hit the gym", "need to get back to the gym"),
    ("learn spanish", "start learning spanish"),
    ("call mom more", "want to call my mother more often"),
    ("save money", "get better at saving money"),
    ("start writing again", "get back into writing"),
    ("learn piano", "want to play the piano"),
    ("read more", "want to read more books"),
    ("get fit", "get back in shape"),
    ("meditate regularly", "start a meditation habit"),
    ("cut back on caffeine", "drink less coffee"),
    ("walk more", "go for more walks"),
    ("learn to cook", "get better at cooking"),
]

# (a, b) DISTINCT intentions -> must NOT merge. These set the split floor.
SHOULD_SPLIT = [
    ("learn spanish", "learn guitar"),
    ("get back to the gym", "eat healthier"),
    ("save money", "call mom more"),
    ("learn piano", "learn spanish"),
    ("start writing again", "declutter the garage"),
    ("walk more", "cut back on caffeine"),
    ("read more books", "save money"),
    ("learn to cook", "get back to the gym"),
    ("start therapy", "learn spanish"),
    ("call mom more", "learn guitar"),
    ("meditate regularly", "save money"),
    ("get fit", "learn piano"),
]

THRESHOLDS = [0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94]
# gemini-embedding has its own shallow Vertex quota; pace + back off so a burst
# doesn't wall the run (STATE: pre-launch quota item).
_PACE_S = float(os.getenv("INTENTION_EVAL_DELAY", "4"))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def _embed_paced(text: str, max_attempts: int = 8):
    for attempt in range(max_attempts):
        try:
            return await get_embedding(text)
        except Exception as exc:
            msg = str(exc).lower()
            is_rate = "429" in msg or "resource_exhausted" in msg or "exhausted" in msg or "quota" in msg
            if not is_rate or attempt == max_attempts - 1:
                raise
            backoff = _PACE_S * (2 ** attempt) + random.uniform(0, 1.0)
            print(f"   [429] embedding backoff {backoff:.1f}s (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(backoff)


async def _embed_all(phrases: list[str]) -> dict:
    """Embed each unique phrase once (paced + backed off for the embedding QPM),
    task_type matched to the resolver's default (RETRIEVAL_DOCUMENT)."""
    cache: dict = {}
    unique = sorted(set(phrases))
    for i, p in enumerate(unique):
        cache[p] = await _embed_paced(p)
        if i + 1 < len(unique):
            await asyncio.sleep(_PACE_S)
    return cache


async def run() -> dict:
    phrases = [p for pair in SHOULD_MERGE + SHOULD_SPLIT for p in pair]
    vecs = await _embed_all(phrases)

    merge_sims = sorted((round(cosine(vecs[a], vecs[b]), 4) for a, b in SHOULD_MERGE), reverse=True)
    split_sims = sorted((round(cosine(vecs[a], vecs[b]), 4) for a, b in SHOULD_SPLIT), reverse=True)

    # For each threshold: a SHOULD_SPLIT pair with sim >= T is a FALSE MERGE
    # (the unrecoverable error); a SHOULD_MERGE pair with sim < T is a false split.
    sweep = []
    for t in THRESHOLDS:
        false_merges = sum(1 for s in split_sims if s >= t)
        false_splits = sum(1 for s in merge_sims if s < t)
        sweep.append({
            "threshold": t,
            "false_merges": false_merges,
            "false_splits": false_splits,
            "merges_kept": len(merge_sims) - false_splits,
        })

    split_max = max(split_sims) if split_sims else None
    # Bias-to-split recommendation: the lowest swept threshold with ZERO false
    # merges (sits just above the distinct-pair max), so no real intention is
    # silently destroyed.
    zero_merge = [row for row in sweep if row["false_merges"] == 0]
    recommended = min((row["threshold"] for row in zero_merge), default=None)

    summary = {
        "n_should_merge": len(SHOULD_MERGE),
        "n_should_split": len(SHOULD_SPLIT),
        "merge_pair_cosine": {"max": merge_sims[0], "min": merge_sims[-1],
                              "median": merge_sims[len(merge_sims) // 2]},
        "split_pair_cosine": {"max": split_sims[0], "min": split_sims[-1],
                              "median": split_sims[len(split_sims) // 2]},
        "split_max": split_max,
        "sweep": sweep,
        "recommended_threshold": recommended,
        "bias": "split (recommended = lowest threshold with zero false merges)",
        "provider": "vertex" if os.getenv("USE_VERTEX") else "ai_studio",
    }

    print("\n=== merge-pair cosines (should be high) ===")
    print(" ", merge_sims)
    print("=== split-pair cosines (distinct; threshold must sit above max) ===")
    print(" ", split_sims, f"  max={split_max}")
    print("\nthreshold  false_merges  false_splits  merges_kept")
    for row in sweep:
        flag = "  <- recommended" if row["threshold"] == recommended else ""
        print(f"  {row['threshold']:.2f}        {row['false_merges']:>2}            "
              f"{row['false_splits']:>2}            {row['merges_kept']:>2}/{len(merge_sims)}{flag}")
    print(f"\nRECOMMENDED (bias to split, zero false merges): {recommended}")

    if os.getenv("SAVE_RESULTS"):
        results = (
            [{"case_id": f"merge::{a}|{b}", "kind": "should_merge", "cosine": round(cosine(vecs[a], vecs[b]), 4)}
             for a, b in SHOULD_MERGE]
            + [{"case_id": f"split::{a}|{b}", "kind": "should_split", "cosine": round(cosine(vecs[a], vecs[b]), 4)}
               for a, b in SHOULD_SPLIT]
        )
        path = save_results("intention_threshold_calibration", summary, results)
        print(f"Wrote {path}")
    return summary


if __name__ == "__main__":
    asyncio.run(run())
