PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'teacher')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS student_profiles (
    user_id  INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    grade    INTEGER NOT NULL CHECK (grade BETWEEN 6 AND 10),
    language TEXT NOT NULL DEFAULT 'en',
    school   TEXT,
    level    TEXT NOT NULL DEFAULT 'beginner'
);

CREATE TABLE IF NOT EXISTS subjects (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS student_subjects (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, subject_id)
);

CREATE TABLE IF NOT EXISTS topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id      INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    grade_min       INTEGER NOT NULL DEFAULT 6,
    prerequisite_id INTEGER REFERENCES topics(id),
    sort_order      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS questions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id       INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    difficulty     INTEGER NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 3),
    language       TEXT NOT NULL DEFAULT 'en',
    question_text  TEXT NOT NULL,
    option_a       TEXT NOT NULL,
    option_b       TEXT NOT NULL,
    option_c       TEXT NOT NULL,
    option_d       TEXT NOT NULL,
    correct_option TEXT NOT NULL CHECK (correct_option IN ('A', 'B', 'C', 'D')),
    explanation    TEXT,
    source         TEXT NOT NULL DEFAULT 'bank' CHECK (source IN ('bank', 'ai')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id        INTEGER NOT NULL REFERENCES topics(id),
    difficulty      INTEGER NOT NULL DEFAULT 1,
    score           INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS attempt_answers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id      INTEGER NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    question_id     INTEGER NOT NULL REFERENCES questions(id),
    selected_option TEXT,
    is_correct      INTEGER NOT NULL DEFAULT 0,
    answered_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per student per topic: this table drives weak-topic detection
CREATE TABLE IF NOT EXISTS topic_performance (
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id           INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    attempts           INTEGER NOT NULL DEFAULT 0,
    questions_answered INTEGER NOT NULL DEFAULT 0,
    correct_answers    INTEGER NOT NULL DEFAULT 0,
    accuracy           REAL NOT NULL DEFAULT 0,
    current_difficulty INTEGER NOT NULL DEFAULT 1,
    status             TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'weak', 'average', 'strong')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, topic_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL CHECK (action_type IN ('revise', 'learn', 'quiz')),
    message     TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_attempts_user ON quiz_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_answers_attempt ON attempt_answers(attempt_id);
CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic_id, difficulty, language);