CREATE TABLE user_memory (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  memory_text TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id)
);

CREATE INDEX idx_user_memory_user_id ON user_memory(user_id);

ALTER TABLE user_memory ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own memory"
  ON user_memory FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can upsert own memory"
  ON user_memory FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own memory"
  ON user_memory FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Service can delete compacted messages"
  ON ask_messages FOR DELETE
  USING (auth.uid() = user_id);
