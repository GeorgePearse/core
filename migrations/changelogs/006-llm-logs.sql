--liquibase formatted sql

--changeset genesis:006-create-llm-logs
CREATE TABLE llm_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    model               TEXT NOT NULL,
    messages            JSONB NOT NULL DEFAULT '[]',
    response            TEXT NOT NULL DEFAULT '',
    thought             TEXT NOT NULL DEFAULT '',
    cost                DOUBLE PRECISION NOT NULL DEFAULT 0,
    execution_time      DOUBLE PRECISION NOT NULL DEFAULT 0,
    metadata            JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_llm_logs_timestamp ON llm_logs(timestamp DESC);
CREATE INDEX idx_llm_logs_model ON llm_logs(model);
--rollback DROP TABLE llm_logs;
