-- Migration 013: Daily LLM cost tracking per user + atomic increment RPC

CREATE TABLE IF NOT EXISTS public.daily_llm_costs (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  date DATE NOT NULL,
  cost_usd DECIMAL(10, 6) NOT NULL DEFAULT 0,
  request_count INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_llm_costs_user_date
  ON public.daily_llm_costs(user_id, date);

-- Atomic additive upsert — safe to call concurrently.
-- Adds p_cost to today's running total; creates the row if it doesn't exist yet.
CREATE OR REPLACE FUNCTION public.increment_daily_cost(
  p_user_id UUID,
  p_date DATE,
  p_cost DECIMAL
) RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.daily_llm_costs (user_id, date, cost_usd, request_count)
  VALUES (p_user_id, p_date, p_cost, 1)
  ON CONFLICT (user_id, date)
  DO UPDATE SET
    cost_usd = public.daily_llm_costs.cost_usd + EXCLUDED.cost_usd,
    request_count = public.daily_llm_costs.request_count + 1,
    updated_at = NOW();
END;
$$;
