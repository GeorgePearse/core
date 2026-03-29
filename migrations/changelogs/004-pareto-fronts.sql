--liquibase formatted sql

--changeset genesis:004-create-pareto-fronts
CREATE TABLE pareto_fronts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES evolution_runs(run_id) ON DELETE CASCADE,
    generation          INTEGER NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    individual_id       UUID NOT NULL,
    fitness_score       DOUBLE PRECISION NOT NULL DEFAULT 0,
    combined_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    metrics             JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_pareto_fronts_run_gen ON pareto_fronts(run_id, generation);
CREATE INDEX idx_pareto_fronts_score ON pareto_fronts(fitness_score DESC);
--rollback DROP TABLE pareto_fronts;
