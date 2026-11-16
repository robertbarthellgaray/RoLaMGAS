-- Same user-requested ceiling for the Jupiter prefix, separately archived.
CREATE TABLE IF NOT EXISTS edvej_c3_purge_20261116 AS SELECT * FROM candidates WHERE 0;
CREATE UNIQUE INDEX IF NOT EXISTS edvej_c3_purge_id ON edvej_c3_purge_20261116(id);
INSERT OR IGNORE INTO edvej_c3_purge_20261116 SELECT * FROM candidates
WHERE sequence='EdvEJ' AND c3>60;
DELETE FROM candidates WHERE sequence='EdvEJ' AND c3>60
AND id IN (SELECT id FROM edvej_c3_purge_20261116);
CREATE TRIGGER IF NOT EXISTS edvej_c3_insert_guard BEFORE INSERT ON candidates
WHEN NEW.sequence='EdvEJ' AND NEW.c3>60
BEGIN SELECT RAISE(ABORT,'EdvEJ public-library C3 exceeds 60'); END;
CREATE TRIGGER IF NOT EXISTS edvej_c3_update_guard BEFORE UPDATE OF sequence,c3 ON candidates
WHEN NEW.sequence='EdvEJ' AND NEW.c3>60
BEGIN SELECT RAISE(ABORT,'EdvEJ public-library C3 exceeds 60'); END;
