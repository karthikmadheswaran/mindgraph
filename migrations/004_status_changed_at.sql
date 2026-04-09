ALTER TABLE deadlines
ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;

ALTER TABLE projects
ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMPTZ;

UPDATE projects
SET status = 'hidden'
WHERE status = 'archived';

UPDATE deadlines
SET status_changed_at = NOW()
WHERE status IN ('done', 'missed')
  AND status_changed_at IS NULL;

UPDATE projects
SET status_changed_at = NOW()
WHERE status IN ('completed', 'hidden')
  AND status_changed_at IS NULL;

CREATE TABLE IF NOT EXISTS suppressed_project_entities (
    user_id UUID NOT NULL,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_suppressed_project_entities_user
ON suppressed_project_entities(user_id);

CREATE OR REPLACE FUNCTION sync_project_from_entity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.entity_type = 'project' THEN
        IF EXISTS (
            SELECT 1
            FROM suppressed_project_entities
            WHERE user_id = NEW.user_id
              AND entity_id = NEW.id
        ) THEN
            RETURN NEW;
        END IF;

        INSERT INTO projects (
            id,
            user_id,
            name,
            status,
            first_mentioned_at,
            last_mentioned_at,
            mention_count,
            running_summary,
            source_entity_id,
            status_changed_at
        ) VALUES (
            gen_random_uuid(),
            NEW.user_id,
            NEW.name,
            'active',
            NEW.first_seen_at,
            NEW.last_seen_at,
            COALESCE(NEW.mention_count, 1),
            NEW.context_summary,
            NEW.id,
            COALESCE(NEW.last_seen_at, NEW.first_seen_at, NOW())
        )
        ON CONFLICT (source_entity_id) DO UPDATE SET
            name = EXCLUDED.name,
            first_mentioned_at = COALESCE(projects.first_mentioned_at, EXCLUDED.first_mentioned_at),
            last_mentioned_at = EXCLUDED.last_mentioned_at,
            mention_count = EXCLUDED.mention_count,
            running_summary = EXCLUDED.running_summary,
            status = CASE
                WHEN projects.status IN ('hidden', 'completed') THEN projects.status
                ELSE 'active'
            END,
            status_changed_at = CASE
                WHEN projects.status IN ('hidden', 'completed') THEN projects.status_changed_at
                ELSE COALESCE(projects.status_changed_at, EXCLUDED.status_changed_at)
            END;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
