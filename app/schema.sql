-- Login audit log
CREATE TABLE IF NOT EXISTS login_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT    NOT NULL,
    logged_in_at TEXT  NOT NULL DEFAULT (datetime('now','localtime')),
    ip_address TEXT
);

-- Team members (replaces accounts.csv)
CREATE TABLE IF NOT EXISTS team_member (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    first_name  TEXT    NOT NULL DEFAULT '',
    middle_name TEXT    NOT NULL DEFAULT '',
    last_name   TEXT    NOT NULL DEFAULT '',
    name        TEXT    NOT NULL DEFAULT '',  -- full name (first [middle] last), kept for bulk matching
    team        TEXT    NOT NULL,
    email       TEXT
);

-- Users (for forecasting joins)
CREATE TABLE IF NOT EXISTS user (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT    NOT NULL UNIQUE,
    full_name      TEXT    NOT NULL,
    title          TEXT    NOT NULL DEFAULT '',
    is_a_team_lead BOOLEAN NOT NULL DEFAULT 0,
    reports_to     INTEGER REFERENCES user(user_id)
);

-- Projects
CREATE TABLE IF NOT EXISTS project (
    project_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_number       INTEGER NOT NULL,
    project_task_number  INTEGER NOT NULL,
    project_name         TEXT    NOT NULL,
    company              TEXT    NOT NULL,
    progress             TEXT    NOT NULL DEFAULT '',
    utilization          TEXT    NOT NULL DEFAULT '',
    project_manager      INTEGER REFERENCES user(user_id) ON DELETE CASCADE
);

-- Project assignments
CREATE TABLE IF NOT EXISTS project_assignment (
    project_assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id            INTEGER REFERENCES project(project_id) ON DELETE CASCADE,
    user_id               INTEGER REFERENCES user(user_id)       ON DELETE CASCADE,
    project_hours         REAL
);

-- Forecast
CREATE TABLE IF NOT EXISTS forecast (
    forecast_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    progress     TEXT    NOT NULL DEFAULT '',
    task_id      INTEGER,
    customer     TEXT    NOT NULL DEFAULT '',
    sow          TEXT    NOT NULL DEFAULT '',
    utilization  TEXT    NOT NULL DEFAULT '',
    project_name TEXT    REFERENCES project(project_name) ON DELETE CASCADE,
    team         TEXT    NOT NULL DEFAULT '',
    pm           INTEGER REFERENCES user(user_id) ON DELETE CASCADE,
    team_lead    INTEGER REFERENCES user(user_id) ON DELETE CASCADE,
    sub_org      TEXT    NOT NULL DEFAULT '',
    cost         TEXT    NOT NULL DEFAULT '',
    resources    INTEGER REFERENCES user(user_id) ON DELETE CASCADE,
    role         TEXT    NOT NULL DEFAULT '',
    hrs_rate     TEXT,
    perc         TEXT,
    alloc        INTEGER,
    con          REAL,
    forecast     INTEGER NOT NULL DEFAULT 0,
    rem          INTEGER NOT NULL DEFAULT 0
);

-- Non-billable project names (project title substrings that are always non-billable)
CREATE TABLE IF NOT EXISTS nonbillable_project (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT    NOT NULL UNIQUE
);

-- Username corrections: maps Excel-derived username → correct Q360 username
CREATE TABLE IF NOT EXISTS username_map (
    employee_name TEXT PRIMARY KEY,  -- Full name from Excel (e.g. "Asokan Gunanathan")
    q360_username TEXT NOT NULL      -- Correct Q360 username (e.g. "AGUNANATHAN@CON")
);

-- Bulk upload default type config
CREATE TABLE IF NOT EXISTS bulk_config (
    key      TEXT PRIMARY KEY,
    project  TEXT NOT NULL DEFAULT '',
    q360id   TEXT NOT NULL DEFAULT ''
);

-- Bulk upload submitted hours log (for Forecast view)
CREATE TABLE IF NOT EXISTS bulk_hours (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL,
    employee     TEXT NOT NULL DEFAULT '',
    q360id       TEXT NOT NULL,
    project      TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT '',
    company      TEXT NOT NULL DEFAULT '',
    date         TEXT NOT NULL,           -- YYYY-MM-DD
    hours        REAL NOT NULL,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    timebillno   TEXT
);

-- Pay periods: each period has 2 weeks (Mon–Sun each), label format YYYY-N
CREATE TABLE IF NOT EXISTS pay_period (
    pay_period  TEXT PRIMARY KEY,  -- e.g. '2025-23'
    week1_start TEXT NOT NULL,     -- YYYY-MM-DD (Monday)
    week1_end   TEXT NOT NULL,     -- YYYY-MM-DD (Sunday)
    week2_start TEXT NOT NULL,     -- YYYY-MM-DD (Monday)
    week2_end   TEXT NOT NULL      -- YYYY-MM-DD (Sunday)
);

-- Overtime records: processed output rows saved on each parse
CREATE TABLE IF NOT EXISTS overtime_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT,               -- ID from source form
    name            TEXT NOT NULL,
    start_time      TEXT,
    completion_time TEXT,
    date            TEXT,               -- display date e.g. 2/12/2026
    client          TEXT,
    work            TEXT,
    extra_hours     REAL,
    pay_period      TEXT,
    pay_week        INTEGER,
    submitted_by    TEXT,               -- logged-in user who ran the parse
    parsed_at       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Forecast weeks
CREATE TABLE IF NOT EXISTS forecast_week (
    forecast_week_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id          INTEGER REFERENCES forecast(forecast_id) ON DELETE CASCADE,
    week             TEXT,
    custom           TEXT,
    hr               INTEGER
);
