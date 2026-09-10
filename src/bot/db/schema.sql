CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phash TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    image_file_id TEXT,
    created_at TEXT NOT NULL,
    question_type TEXT,
    consensus_answer TEXT,
    consensus_state TEXT NOT NULL,
    resolved_by_tier TEXT NOT NULL DEFAULT 'single',
    ground_truth TEXT,
    user_id INTEGER NOT NULL,
    consensus_json TEXT NOT NULL,
    served_from_cache INTEGER NOT NULL DEFAULT 0,
    source_question_id INTEGER REFERENCES questions(id),
    reduced_model_set INTEGER NOT NULL DEFAULT 0,
    transcription_divergence INTEGER NOT NULL DEFAULT 0,
    min_transcription_overlap REAL
);

CREATE INDEX IF NOT EXISTS idx_questions_phash ON questions(phash);
CREATE INDEX IF NOT EXISTS idx_questions_created_at ON questions(created_at);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    model_id TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'single',
    answer TEXT,
    confidence REAL,
    raw_json TEXT,
    latency_ms INTEGER NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_attempts_question_id ON attempts(question_id);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    added_at TEXT NOT NULL,
    daily_count INTEGER NOT NULL DEFAULT 0,
    daily_count_date TEXT,
    is_allowed INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS spend_days (
    day TEXT PRIMARY KEY,
    reserved_usd REAL NOT NULL DEFAULT 0,
    actual_usd REAL NOT NULL DEFAULT 0
);
