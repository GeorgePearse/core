--liquibase formatted sql

--changeset genesis:003-create-individuals
CREATE TABLE individuals (
    run_id              UUID NOT NULL REFERENCES evolution_runs(run_id) ON DELETE CASCADE,
    individual_id       UUID NOT NULL DEFAULT gen_random_uuid(),
    generation          INTEGER NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    parent_id           UUID,
    mutation_type       TEXT NOT NULL,
    fitness_score       DOUBLE PRECISION NOT NULL DEFAULT 0,
    combined_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    metrics             JSONB NOT NULL DEFAULT '{}',
    is_pareto           BOOLEAN NOT NULL DEFAULT false,
    api_cost            DOUBLE PRECISION NOT NULL DEFAULT 0,
    embed_cost          DOUBLE PRECISION NOT NULL DEFAULT 0,
    novelty_cost        DOUBLE PRECISION NOT NULL DEFAULT 0,
    code_hash           TEXT NOT NULL DEFAULT '',
    code_size           INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (run_id, individual_id)
);

CREATE INDEX idx_individuals_run_gen ON individuals(run_id, generation);
CREATE INDEX idx_individuals_score ON individuals(combined_score DESC);
CREATE INDEX idx_individuals_parent ON individuals(parent_id);
--rollback DROP TABLE individuals;
