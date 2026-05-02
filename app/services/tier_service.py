import logging
import os

from app.db import supabase

logger = logging.getLogger(__name__)
TIER_TTL = 3600  # seconds


class TierService:
    def __init__(self):
        self._redis = None
        self._redis_attempted = False

    def _redis_client(self):
        if self._redis_attempted:
            return self._redis
        self._redis_attempted = True
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            return None
        try:
            from upstash_redis.asyncio import Redis

            self._redis = Redis(url=url, token=token)
            return self._redis
        except Exception as e:
            logger.warning("Upstash Redis unavailable: %s", e)
            return None

    async def get_user_tier(self, user_id: str) -> str:
        redis = self._redis_client()
        cache_key = f"user_tier:{user_id}"

        if redis:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    return cached if isinstance(cached, str) else cached.decode()
            except Exception as e:
                logger.warning("Redis tier get failed for %s: %s", user_id, e)

        result = (
            supabase.from_("users")
            .select("subscription_tier")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        tier = rows[0].get("subscription_tier", "free") if rows else "free"

        if redis:
            try:
                await redis.set(cache_key, tier, ex=TIER_TTL)
            except Exception as e:
                logger.warning("Redis tier set failed for %s: %s", user_id, e)

        return tier

    async def invalidate(self, user_id: str) -> None:
        redis = self._redis_client()
        if redis:
            try:
                await redis.delete(f"user_tier:{user_id}")
            except Exception:
                pass


tier_service = TierService()
