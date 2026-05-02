-- Migration 011: Billing history table (provider-agnostic — works with Razorpay, PayU, Paddle, etc.)

CREATE TABLE IF NOT EXISTS public.subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  payment_provider TEXT,              -- 'razorpay', 'payu', 'paddle', etc.
  provider_subscription_id TEXT,      -- provider's subscription reference
  provider_customer_id TEXT,          -- provider's customer reference
  tier TEXT NOT NULL DEFAULT 'free'
    CHECK (tier IN ('free', 'pro')),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'canceled', 'past_due', 'trialing', 'paused')),
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id
  ON public.subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_provider_sub
  ON public.subscriptions(provider_subscription_id);
