BEGIN;

CREATE TABLE conversation_memory_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL,
    owner_type VARCHAR(32) NOT NULL,
    owner_reference VARCHAR(255) NOT NULL,
    student_id BIGINT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL CHECK (char_length(content) <= 4000),
    selected_agents JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(selected_agents) = 'array'),
    interaction_status VARCHAR(16) NOT NULL
        CHECK (interaction_status IN ('completed', 'partial')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_conversation_memory_scope_order
ON conversation_memory_messages
    (conversation_id, owner_type, owner_reference, student_id, id);

CREATE TABLE telegram_conversation_mappings (
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    conversation_id UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (telegram_user_id, telegram_chat_id)
);

COMMIT;
