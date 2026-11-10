CREATE TABLE IF NOT EXISTS candidates (
 id TEXT PRIMARY KEY, target TEXT NOT NULL, sequence TEXT NOT NULL,
 launch_jd REAL NOT NULL, arrival_jd REAL NOT NULL, c3 REAL NOT NULL,
 classification TEXT NOT NULL CHECK(classification IN ('pass','yellow')),
 solved_at TEXT NOT NULL, received_at TEXT NOT NULL, payload TEXT NOT NULL,
 added_at TEXT NOT NULL, added_at_basis TEXT NOT NULL DEFAULT 'server receipt',
 encounter_key TEXT NOT NULL, selection_score REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS candidate_target_energy ON candidates(target,c3,launch_jd);
CREATE INDEX IF NOT EXISTS candidate_target_time ON candidates(target,received_at DESC);
CREATE TABLE IF NOT EXISTS daily_budget (day TEXT PRIMARY KEY, submissions INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS candidate_received ON candidates(received_at DESC,id);
CREATE UNIQUE INDEX IF NOT EXISTS candidate_encounter_unique ON candidates(encounter_key);
