--liquibase formatted sql

--changeset genesis:007-create-agent-actions
CREATE TABLE agent_actions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    action_type         TEXT NOT NULL,
    details             JSONB NOT NULL DEFAULT '{}',
    metadata            JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_agent_actions_timestamp ON agent_actions(timestamp DESC);
CREATE INDEX idx_agent_actions_type ON agent_actions(action_type);
--rollback DROP TABLE agent_actions;
