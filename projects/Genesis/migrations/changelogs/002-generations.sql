--liquibase formatted sql

--changeset genesis:002-create-generations
CREATE TABLE generations (
    run_id              UUID NOT NULL REFERENCES evolution_runs(run_id) ON DELETE CASCADE,
    generation          INTEGER NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    num_individuals     INTEGER NOT NULL DEFAULT 0,
    best_score          DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_score           DOUBLE PRECISION NOT NULL DEFAULT 0,
    pareto_size         INTEGER NOT NULL DEFAULT 0,
    total_cost          DOUBLE PRECISION NOT NULL DEFAULT 0,
    metadata            JSONB NOT NULL DEFAULT '{}',

    PRIMARY KEY (run_id, generation)
);

CREATE INDEX idx_generations_run ON generations(run_id);
--rollback DROP TABLE generations;
