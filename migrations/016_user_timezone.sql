-- Migration 016: Add timezone column to public.users
-- public.users already exists from migration 010 (subscription_tier).

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';

COMMENT ON COLUMN public.users.timezone IS
  'User home timezone (IANA). Set on first entry submission; updateable via settings. Used as fallback when Ask request does not include browser timezone.';
