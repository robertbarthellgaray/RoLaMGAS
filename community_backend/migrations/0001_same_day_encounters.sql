-- One-time migration for the pre-encounter-key production schema.
-- First export the complete remote D1 database to a PRIVATE backup file.
-- TDB calendar days use floor(JD+0.5); validated epochs are all positive.
ALTER TABLE candidates ADD COLUMN encounter_key TEXT;
ALTER TABLE candidates ADD COLUMN selection_score REAL NOT NULL DEFAULT 1e99;
UPDATE candidates SET
 encounter_key=(SELECT group_concat(value,'/') FROM json_each(candidates.payload,'$.body_ids')) || '@' ||
  (SELECT group_concat(CAST(value+0.5 AS INTEGER),'/') FROM json_each(candidates.payload,'$.dates_jd_tdb')),
 selection_score=json_extract(payload,'$.metrics.launch_c3_km2_s2')/100.0 +
  json_extract(payload,'$.metrics.total_dsm_kms') +
  json_extract(payload,'$.metrics.arrival_vinf_kms')/20.0 + (arrival_jd-launch_jd)/365.25/100.0;
DELETE FROM candidates WHERE id IN (
 SELECT id FROM (
  SELECT id,ROW_NUMBER() OVER (
   PARTITION BY encounter_key ORDER BY CASE classification WHEN 'pass' THEN 0 ELSE 1 END,selection_score,id
  ) AS duplicate_number FROM candidates
 ) WHERE duplicate_number>1
);
CREATE UNIQUE INDEX candidate_encounter_unique ON candidates(encounter_key);
-- The previous Worker omits this column. Block that brief deploy-transition
-- write window rather than allowing nullable duplicate slots into the migration.
CREATE TRIGGER candidate_encounter_required BEFORE INSERT ON candidates
WHEN NEW.encounter_key IS NULL
BEGIN SELECT RAISE(ABORT,'The library Worker must supply an encounter key'); END;
