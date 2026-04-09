WITH ranked_deadlines AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY source_entry_id, lower(description), due_date
            ORDER BY id
        ) AS rn
    FROM deadlines
)
DELETE FROM deadlines
WHERE id IN (
    SELECT id
    FROM ranked_deadlines
    WHERE rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_deadlines_source_entry_description_due_date
ON deadlines (source_entry_id, lower(description), due_date);
