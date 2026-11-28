-- Index the same expression used by the existing duplicate-handling triggers.
-- Installed on production 2026-11-27; preserves all existing candidate records.
CREATE INDEX IF NOT EXISTS candidate_same_launch_day
 ON candidates(target,sequence,CAST(launch_jd+.5 AS INTEGER));
