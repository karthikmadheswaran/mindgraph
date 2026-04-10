CREATE TABLE ask_messages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_ask_messages_user_id ON ask_messages(user_id);
CREATE INDEX idx_ask_messages_user_created ON ask_messages(user_id, created_at DESC);

ALTER TABLE ask_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own messages"
  ON ask_messages FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own messages"
  ON ask_messages FOR INSERT
  WITH CHECK (auth.uid() = user_id);
