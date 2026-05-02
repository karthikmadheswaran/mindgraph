-- Migration 012: Rate limit usage tracking + atomic RPC

CREATE TABLE IF NOT EXISTS public.rate_limit_usage (
  id BIGSERIAL PRIMARY KEY,
  key TEXT NOT NULL,          -- 'user:{uuid}:entries', 'user:{uuid}:asks', 'ip:{addr}:all'
  window_start TIMESTAMPTZ NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(key, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_usage_key_window
  ON public.rate_limit_usage(key, window_start);

-- Atomic rate limit check-and-increment.
-- Increments the counter only when under the limit.
-- Returns TRUE if the request is allowed (count was under limit before this call).
-- Returns FALSE if the request should be rejected (already at or over limit).
CREATE OR REPLACE FUNCTION public.try_rate_limit(
  p_key TEXT,
  p_window_start TIMESTAMPTZ,
  p_limit INTEGER
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  new_count INTEGER;
BEGIN
  INSERT INTO public.rate_limit_usage (key, window_start, count)
  VALUES (p_key, p_window_start, 1)
  ON CONFLICT (key, window_start)
  DO UPDATE SET
    count = CASE
      WHEN public.rate_limit_usage.count < p_limit
        THEN public.rate_limit_usage.count + 1
      ELSE public.rate_limit_usage.count
    END,
    updated_at = NOW()
  RETURNING count INTO new_count;

  RETURN new_count <= p_limit;
END;
$$;
