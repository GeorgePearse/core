--liquibase formatted sql

--changeset genesis:001-create-evolution-runs
CREATE TABLE evolution_runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    start_time          TIMESTAMPTZ NOT NULL DEFAULT now(),
    end_time            TIMESTAMPTZ,
    task_name           TEXT NOT NULL,
    config              JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'running',
    total_generations   INTEGER NOT NULL DEFAULT 0,
    population_size     INTEGER NOT NULL DEFAULT 0,
    cluster_type        TEXT,
    database_path       TEXT
);

CREATE INDEX idx_evolution_runs_task ON evolution_runs(task_name);
CREATE INDEX idx_evolution_runs_status ON evolution_runs(status);
CREATE INDEX idx_evolution_runs_start_time ON evolution_runs(start_time DESC);
--rollback DROP TABLE evolution_runs;
