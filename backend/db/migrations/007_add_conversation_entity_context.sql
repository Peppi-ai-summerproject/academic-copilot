ALTER TABLE conversation_memory_messages
    ADD COLUMN IF NOT EXISTS resolved_entities JSONB NOT NULL DEFAULT '[]'::jsonb;
