import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STAGE_LIMITS_MS = {
    "conversation_fetch": 200,
    "memory_fetch": 200,
    "embedding": 1000,
    "vector_search": 300,
    "bm25_search": 200,
    "merge_and_boost": 50,
    "rerank": 1500,
    "prompt_build": 50,
    "llm_generation": 8000,
}


@dataclass
class LatencyTrace:
    """Tracks latency for each stage of the Ask pipeline."""

    stages: dict = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str):
        t0 = time.perf_counter()
        yield
        self.stages[name] = (time.perf_counter() - t0) * 1000

    @property
    def total_ms(self) -> float:
        return sum(self.stages.values())

    def summary(self) -> dict:
        return {
            "stages": {k: round(v, 1) for k, v in self.stages.items()},
            "total_ms": round(self.total_ms, 1),
        }

    def log(self, query_preview: str = ""):
        preview = query_preview[:50] + "..." if len(query_preview) > 50 else query_preview
        parts = " | ".join(f"{k}: {v:.0f}ms" for k, v in self.stages.items())
        logger.info("ASK LATENCY [%s] %s | TOTAL: %.0fms", preview, parts, self.total_ms)

        for stage_name, elapsed in self.stages.items():
            limit = STAGE_LIMITS_MS.get(stage_name)
            if limit and elapsed > limit:
                logger.warning(
                    "ASK LATENCY WARNING: %s took %.0fms (limit: %dms) for query [%s]",
                    stage_name,
                    elapsed,
                    limit,
                    preview,
                )
