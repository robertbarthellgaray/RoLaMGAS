-- Filled through the reviewed cleanup audit. Named reconstructions and entries
-- that merely need physics revalidation are preserved, not excluded here.
CREATE TABLE IF NOT EXISTS candidate_exclusions(id TEXT PRIMARY KEY,reason TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS candidate_excluded_guard BEFORE INSERT ON candidates
WHEN EXISTS(SELECT 1 FROM candidate_exclusions WHERE id=NEW.id)
BEGIN SELECT RAISE(IGNORE); END;
INSERT OR IGNORE INTO candidate_preserved VALUES('faaebce61e7087814c1e25522e0daa12697e5c8526c11d68c7bfa3e749d7023d','Named Pioneer 11-inspired reconstruction; retain review warning');
INSERT OR IGNORE INTO candidate_preserved VALUES('72be12f1d7161478b149716766f4432aeaa5f495f29bd8fcdc9437aebf42d5af','Previously identified Pioneer 11 reconstruction; preserve');
