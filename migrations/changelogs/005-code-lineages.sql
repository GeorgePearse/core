--liquibase formatted sql

--changeset genesis:005-create-code-lineages
CREATE TABLE code_lineages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES evolution_runs(run_id) ON DELETE CASCADE,
    child_id            UUID NOT NULL,
    parent_id           UUID,
    generation          INTEGER NOT NULL,
    mutation_type       TEXT NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    fitness_delta       DOUBLE PRECISION NOT NULL DEFAULT 0,
    edit_summary        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_code_lineages_run_gen ON code_lineages(run_id, generation);
CREATE INDEX idx_code_lineages_child ON code_lineages(child_id);
CREATE INDEX idx_code_lineages_parent ON code_lineages(parent_id);
--rollback DROP TABLE code_lineages;
