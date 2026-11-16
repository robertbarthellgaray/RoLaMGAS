-- User-requested public-library curation; not a physical feasibility assertion.
-- Back up complete matching rows before deleting, including original timestamps.
CREATE TABLE IF NOT EXISTS edveju_c3_purge_20261116 AS SELECT * FROM candidates WHERE 0;
CREATE UNIQUE INDEX IF NOT EXISTS edveju_c3_purge_id ON edveju_c3_purge_20261116(id);
INSERT OR IGNORE INTO edveju_c3_purge_20261116 SELECT * FROM candidates
WHERE sequence='EdvEJU' AND c3>60;
DELETE FROM candidates WHERE sequence='EdvEJU' AND c3>60
AND id IN (SELECT id FROM edveju_c3_purge_20261116);
CREATE TRIGGER IF NOT EXISTS edveju_c3_insert_guard BEFORE INSERT ON candidates
WHEN NEW.sequence='EdvEJU' AND NEW.c3>60
BEGIN SELECT RAISE(ABORT,'EdvEJU public-library C3 exceeds 60'); END;
CREATE TRIGGER IF NOT EXISTS edveju_c3_update_guard BEFORE UPDATE OF sequence,c3 ON candidates
WHEN NEW.sequence='EdvEJU' AND NEW.c3>60
BEGIN SELECT RAISE(ABORT,'EdvEJU public-library C3 exceeds 60'); END;
