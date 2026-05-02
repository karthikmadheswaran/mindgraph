-- Migration 010: Add subscription_tier to users
-- IMPORTANT: Before running, check if public.users already exists:
--   SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('users','profiles');
-- If it exists, run only the ALTER TABLE variant instead of CREATE TABLE.

CREATE TABLE IF NOT EXISTS public.users (
  id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
  subscription_tier TEXT NOT NULL DEFAULT 'free'
    CHECK (subscription_tier IN ('free', 'pro')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_subscription_tier
  ON public.users(subscription_tier);

-- Backfill: insert a row for every existing auth user that doesn't have a profile yet
INSERT INTO public.users (id)
SELECT id FROM auth.users
ON CONFLICT (id) DO NOTHING;

-- Auto-insert profile row on new signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.users (id) VALUES (new.id) ON CONFLICT (id) DO NOTHING;
  RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
