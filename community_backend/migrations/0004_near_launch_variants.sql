-- Merge nearby same-launch-day variants atomically, including old clients.
-- Meaningful date/energy/burn/arrival-speed differences remain distinct.
-- Keep every removed payload and a redirect to its retained representative.
CREATE TABLE IF NOT EXISTS candidate_aliases(old_id TEXT PRIMARY KEY,new_id TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_preserved(id TEXT PRIMARY KEY,reason TEXT NOT NULL);
INSERT OR IGNORE INTO candidate_preserved VALUES('864ca8c31892f68454fb39dbed6bbeb3a76f8af3b7d676552f097cb870e862b0','Exact Voyager 1 encounter calendar');
CREATE TABLE IF NOT EXISTS candidate_duplicate_archive(id TEXT PRIMARY KEY,payload TEXT NOT NULL,added_at TEXT,received_at TEXT,reason TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS candidate_same_launch ON candidates(target,sequence,launch_jd);
DROP TRIGGER IF EXISTS candidate_near_ignore;DROP TRIGGER IF EXISTS candidate_near_replace_insert;DROP TRIGGER IF EXISTS candidate_near_replace_update;
CREATE TRIGGER candidate_near_ignore BEFORE INSERT ON candidates
 WHEN EXISTS(SELECT 1 FROM candidates c WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id))
 BEGIN
 INSERT OR REPLACE INTO candidate_duplicate_archive VALUES(NEW.id,NEW.payload,NEW.added_at,NEW.received_at,'Near-identical same-launch-day variant');
 INSERT OR REPLACE INTO candidate_aliases SELECT NEW.id,c.id,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM candidates c
 WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id) ORDER BY CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END,c.selection_score,c.id LIMIT 1;
 SELECT RAISE(IGNORE);
 END;
CREATE TRIGGER candidate_near_replace_insert AFTER INSERT ON candidates
 BEGIN
 INSERT OR REPLACE INTO candidate_duplicate_archive SELECT c.id,c.payload,c.added_at,c.received_at,'Near-identical same-launch-day variant' FROM candidates c WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND NOT (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id);
 INSERT OR REPLACE INTO candidate_aliases SELECT c.id,NEW.id,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM candidates c WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND NOT (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id);
 DELETE FROM candidates WHERE id IN (SELECT c.id FROM candidates c WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND NOT (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id));
 END;
CREATE TRIGGER candidate_near_replace_update AFTER UPDATE ON candidates
 BEGIN
 INSERT OR REPLACE INTO candidate_duplicate_archive SELECT c.id,c.payload,c.added_at,c.received_at,'Near-identical same-launch-day variant' FROM candidates c WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND NOT (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id);
 INSERT OR REPLACE INTO candidate_aliases SELECT c.id,NEW.id,strftime('%Y-%m-%dT%H:%M:%fZ','now') FROM candidates c WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND NOT (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id);
 DELETE FROM candidates WHERE id IN (SELECT c.id FROM candidates c WHERE c.id<>NEW.id AND c.target=NEW.target AND c.sequence=NEW.sequence
 AND NOT EXISTS(SELECT 1 FROM candidate_preserved p WHERE p.id IN (c.id,NEW.id))
 AND CAST(c.launch_jd+.5 AS INTEGER)=CAST(NEW.launch_jd+.5 AS INTEGER)
 AND json_extract(c.payload,'$.body_ids')=json_extract(NEW.payload,'$.body_ids')
 AND json_array_length(c.payload,'$.dates_jd_tdb')=json_array_length(NEW.payload,'$.dates_jd_tdb')
 AND NOT EXISTS(SELECT 1 FROM json_each(c.payload,'$.dates_jd_tdb') a JOIN json_each(NEW.payload,'$.dates_jd_tdb') b ON a.key=b.key WHERE abs(a.value-b.value)>7)
 AND abs(c.c3-NEW.c3)<=max(.5,.02*min(c.c3,NEW.c3))
 AND abs(json_extract(c.payload,'$.metrics.total_dsm_kms')-json_extract(NEW.payload,'$.metrics.total_dsm_kms'))<=.05
 AND abs(json_extract(c.payload,'$.metrics.arrival_vinf_kms')-json_extract(NEW.payload,'$.metrics.arrival_vinf_kms'))<=.2
 AND abs(json_extract(c.payload,'$.metrics.max_vinf_mismatch_mps')-json_extract(NEW.payload,'$.metrics.max_vinf_mismatch_mps'))<=1 AND NOT (CASE c.classification WHEN 'pass' THEN 0 ELSE 1 END, c.selection_score, c.id)<(CASE NEW.classification WHEN 'pass' THEN 0 ELSE 1 END, NEW.selection_score, NEW.id));
 END;
