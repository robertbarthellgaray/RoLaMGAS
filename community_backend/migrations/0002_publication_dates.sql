-- Preserve the original repository receipt independently of later replacements.
-- For existing rows only the earliest retained receipt is known; label it honestly.
ALTER TABLE candidates ADD COLUMN added_at TEXT;
ALTER TABLE candidates ADD COLUMN added_at_basis TEXT NOT NULL DEFAULT 'earliest retained receipt';
UPDATE candidates SET added_at=received_at WHERE added_at IS NULL;
