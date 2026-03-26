-- Add status tracking columns to entries table
-- status: 'processing' | 'completed' | 'error'
-- pipeline_stage: current pipeline node name (null when completed)

ALTER TABLE entries ADD COLUMN status TEXT NOT NULL DEFAULT 'completed';
ALTER TABLE entries ADD COLUMN pipeline_stage TEXT DEFAULT NULL;
