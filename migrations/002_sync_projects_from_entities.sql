ALTER TABLE projects
ADD COLUMN IF NOT EXISTS source_entity_id UUID REFERENCES entities(id) ON DELETE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_source_entity
ON projects(source_entity_id);

CREATE OR REPLACE FUNCTION sync_project_from_entity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.entity_type = 'project' THEN
        INSERT INTO projects (
            id,
            user_id,
            name,
            status,
            first_mentioned_at,
            last_mentioned_at,
            mention_count,
            running_summary,
            source_entity_id
        ) VALUES (
            gen_random_uuid(),
            NEW.user_id,
            NEW.name,
            'active',
            NEW.first_seen_at,
            NEW.last_seen_at,
            COALESCE(NEW.mention_count, 1),
            NEW.context_summary,
            NEW.id
        )
        ON CONFLICT (source_entity_id) DO UPDATE SET
            name = EXCLUDED.name,
            last_mentioned_at = EXCLUDED.last_mentioned_at,
            mention_count = EXCLUDED.mention_count,
            running_summary = EXCLUDED.running_summary;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_project_entity ON entities;

CREATE TRIGGER trg_sync_project_entity
AFTER INSERT OR UPDATE ON entities
FOR EACH ROW
EXECUTE FUNCTION sync_project_from_entity();

DELETE FROM projects
WHERE name = 'ProjectX'
  AND running_summary LIKE 'Initial test insert%';
