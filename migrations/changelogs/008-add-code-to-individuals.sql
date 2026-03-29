--liquibase formatted sql

--changeset genesis:008-add-code-to-individuals
ALTER TABLE individuals ADD COLUMN code TEXT NOT NULL DEFAULT '';
ALTER TABLE individuals ADD COLUMN language TEXT NOT NULL DEFAULT 'python';
ALTER TABLE individuals ADD COLUMN text_feedback TEXT NOT NULL DEFAULT '';
--rollback ALTER TABLE individuals DROP COLUMN text_feedback; ALTER TABLE individuals DROP COLUMN language; ALTER TABLE individuals DROP COLUMN code;
