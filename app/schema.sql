-- Team members (replaces accounts.csv)
CREATE TABLE IF NOT EXISTS team_member (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT    NOT NULL UNIQUE,
    team     TEXT    NOT NULL,
    email    TEXT
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

-- Forecast weeks
CREATE TABLE IF NOT EXISTS forecast_week (
    forecast_week_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id          INTEGER REFERENCES forecast(forecast_id) ON DELETE CASCADE,
    week             TEXT,
    custom           TEXT,
    hr               INTEGER
);
