-- Remove only public-library entries that cross the documented quality limits.
-- Keep complete original rows privately for recovery; the API reads candidates only.
CREATE TABLE IF NOT EXISTS quality_purge_20261112 AS
 SELECT *, '2026-11-12' AS purged_on, 'small-body quality limits v2' AS purge_reason
 FROM candidates WHERE 0;
CREATE UNIQUE INDEX IF NOT EXISTS quality_purge_20261112_id ON quality_purge_20261112(id);
INSERT OR IGNORE INTO quality_purge_20261112
 SELECT *, '2026-11-12', 'small-body quality limits v2' FROM candidates
 WHERE (CAST(target AS INTEGER) IN (9,999) OR CAST(target AS INTEGER)>=1000)
 AND ((arrival_jd-launch_jd)>=14610 OR (c3>170 AND (arrival_jd-launch_jd)>=9131.25));
DELETE FROM candidates
 WHERE id IN (SELECT id FROM quality_purge_20261112)
 AND (CAST(target AS INTEGER) IN (9,999) OR CAST(target AS INTEGER)>=1000)
 AND ((arrival_jd-launch_jd)>=14610 OR (c3>170 AND (arrival_jd-launch_jd)>=9131.25));
CREATE TRIGGER IF NOT EXISTS candidate_small_body_quality_insert
 BEFORE INSERT ON candidates
 WHEN (CAST(NEW.target AS INTEGER) IN (9,999) OR CAST(NEW.target AS INTEGER)>=1000)
 AND ((NEW.arrival_jd-NEW.launch_jd)>=14610 OR (NEW.c3>170 AND (NEW.arrival_jd-NEW.launch_jd)>=9131.25))
 BEGIN SELECT RAISE(ABORT,'Small-body public-library quality limit'); END;
CREATE TRIGGER IF NOT EXISTS candidate_small_body_quality_update
 BEFORE UPDATE ON candidates
 WHEN (CAST(NEW.target AS INTEGER) IN (9,999) OR CAST(NEW.target AS INTEGER)>=1000)
 AND ((NEW.arrival_jd-NEW.launch_jd)>=14610 OR (NEW.c3>170 AND (NEW.arrival_jd-NEW.launch_jd)>=9131.25))
 BEGIN SELECT RAISE(ABORT,'Small-body public-library quality limit'); END;
