--liquibase formatted sql

--changeset genesis:009-add-correct-to-individuals
ALTER TABLE individuals ADD COLUMN correct BOOLEAN NOT NULL DEFAULT false;
--rollback ALTER TABLE individuals DROP COLUMN correct;
