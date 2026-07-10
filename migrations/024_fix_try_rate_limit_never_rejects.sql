-- Migration 024: fix try_rate_limit — it never rejects (rate limiting is a no-op)
--
-- 🛑 NOT APPLIED. Presented for human review (per autonomy rules: function/schema
--    changes are reported, not auto-applied). Behaviour change — see risk below.
--
-- BUG (found live 2026-07-10 while testing POST /access-requests): the function
-- from migration 012 caps `count` at `p_limit` inside the ON CONFLICT CASE, then
-- returns `new_count <= p_limit`. Once count reaches the limit it is frozen there,
-- so the return is ALWAYS true. Proven directly against prod: 6 consecutive calls
-- with a stable key and p_limit=3 all returned allowed=true.
--
-- Blast radius: EVERY rate limit is affected — free/pro entry & ask limits AND the
-- new access-request IP limit. cost_cap.py is the only remaining spend guard on
-- LLM routes; the unauthenticated /access-requests route has no effective throttle.
-- (App-side keying was also weak — request.client.host = Railway proxy peer — fixed
--  separately in 707708e via X-Forwarded-For; that fix is necessary but the limit
--  still can't reject until THIS migration lands.)
--
-- FIX: drop the cap. Increment unconditionally; the classic pattern allows exactly
-- p_limit requests per window and rejects the (p_limit+1)th. Counter can climb one
-- past the limit per window — harmless (bounded by traffic; window rolls over).
--
-- RISK before applying: this STARTS enforcing limits that have silently never
-- fired. During the demand-test the founder's free-tier account would suddenly hit
-- 5 entries / 7d. Consider bumping the founder to 'pro' (subscriptions/tier) or
-- raising LIMITS first. Apply in staging, re-run the /access-requests burst
-- (4th call in an hour must 429), then prod.

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
    count = public.rate_limit_usage.count + 1,
    updated_at = NOW()
  RETURNING count INTO new_count;

  RETURN new_count <= p_limit;
END;
$$;
