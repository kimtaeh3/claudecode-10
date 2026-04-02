from flask import Flask, redirect, url_for
from app.config import Config
from app import db


def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)
    app.config['DATABASE'] = Config.DATABASE

    db.init_app(app)

    # Auto-initialize DB from schema.sql on every startup (all CREATE TABLE IF NOT EXISTS — idempotent)
    with app.app_context():
        from app.db import init_db as _init_db, get_db as _get_db
        _init_db()
        _db = _get_db()
        # Safe column migrations — add columns that may not exist in older DBs
        _existing = {r[1] for r in _db.execute('PRAGMA table_info(team_member)').fetchall()}
        if 'name' not in _existing:
            _db.execute("ALTER TABLE team_member ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        if 'email' not in _existing:
            _db.execute("ALTER TABLE team_member ADD COLUMN email TEXT")
        if 'member_type' not in _existing:
            _db.execute("ALTER TABLE team_member ADD COLUMN member_type TEXT NOT NULL DEFAULT 'Employee (100%)'")
        if 'start_date' not in _existing:
            _db.execute("ALTER TABLE team_member ADD COLUMN start_date TEXT")
        if 'end_date' not in _existing:
            _db.execute("ALTER TABLE team_member ADD COLUMN end_date TEXT")
        if 'notes' not in _existing:
            _db.execute("ALTER TABLE team_member ADD COLUMN notes TEXT")
        _db.executescript(
            "CREATE TABLE IF NOT EXISTS saved_filter ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username TEXT NOT NULL, "
            "name TEXT NOT NULL, "
            "team TEXT NOT NULL DEFAULT 'All', "
            "start TEXT NOT NULL, "
            "end TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')));"
            "CREATE TABLE IF NOT EXISTS contractor_allocation ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "member_id INTEGER NOT NULL, "
            "project_name TEXT NOT NULL, "
            "utilization_pct REAL NOT NULL DEFAULT 100);"
        )
        # contractor_allocation column migrations
        _ca_cols = {r[1] for r in _db.execute('PRAGMA table_info(contractor_allocation)').fetchall()}
        if 'start_date' not in _ca_cols:
            _db.execute("ALTER TABLE contractor_allocation ADD COLUMN start_date TEXT")
        if 'end_date' not in _ca_cols:
            _db.execute("ALTER TABLE contractor_allocation ADD COLUMN end_date TEXT")
        # saved_filter column migrations
        _sf_cols = {r[1] for r in _db.execute('PRAGMA table_info(saved_filter)').fetchall()}
        if 'usernames' not in _sf_cols:
            _db.execute("ALTER TABLE saved_filter ADD COLUMN usernames TEXT NOT NULL DEFAULT ''")
        if 'project' not in _sf_cols:
            _db.execute("ALTER TABLE saved_filter ADD COLUMN project TEXT NOT NULL DEFAULT ''")
        # User project preference: remembers which task ID to use per username+description
        _db.execute(
            "CREATE TABLE IF NOT EXISTS user_project_pref ("
            "username TEXT NOT NULL, "
            "description TEXT NOT NULL, "
            "task_id TEXT NOT NULL, "
            "updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')), "
            "PRIMARY KEY (username, description))"
        )
        _db.execute(
            "CREATE TABLE IF NOT EXISTS project_cache ("
            "username TEXT PRIMARY KEY, "
            "projects_json TEXT NOT NULL, "
            "fetched_at TEXT NOT NULL DEFAULT (datetime('now','localtime')))"
        )
        # Default non-billable project pattern
        _db.execute(
            "INSERT OR IGNORE INTO nonbillable_project (name) VALUES ('INTERNAL CONNEX')"
        )
        # Pay period table + seed
        _db.execute(
            "CREATE TABLE IF NOT EXISTS pay_period ("
            "pay_period  TEXT PRIMARY KEY, "
            "week1_start TEXT NOT NULL, "
            "week1_end   TEXT NOT NULL, "
            "week2_start TEXT NOT NULL, "
            "week2_end   TEXT NOT NULL)"
        )
        if _db.execute("SELECT COUNT(*) FROM pay_period").fetchone()[0] == 0:
            from datetime import date as _date, timedelta as _td
            # Anchor: 2025-1 Week 1 starts Monday, December 16, 2024 (offset 0).
            # FY 2026-1 starts Monday, December 29, 2025 (offset 27).
            # Each fiscal year has exactly 27 biweekly periods.
            _anchor = _date(2024, 12, 16)
            _PERIODS_PER_FY = 27
            _ANCHOR_FY = 2025
            for _i in range(-5 * _PERIODS_PER_FY, 10 * _PERIODS_PER_FY):
                _w1s = _anchor + _td(days=14 * _i)
                # Fiscal year and 1-indexed period number derived from offset
                if _i >= 0:
                    _fy = _ANCHOR_FY + (_i // _PERIODS_PER_FY)
                    _period = (_i % _PERIODS_PER_FY) + 1
                else:
                    _neg = -_i  # positive count back from anchor
                    _fy = _ANCHOR_FY - ((_neg - 1) // _PERIODS_PER_FY + 1)
                    _period = _PERIODS_PER_FY - ((_neg - 1) % _PERIODS_PER_FY)
                _w1e = _w1s + _td(days=6)
                _w2s = _w1s + _td(days=7)
                _w2e = _w1s + _td(days=13)
                _db.execute(
                    "INSERT OR IGNORE INTO pay_period VALUES (?,?,?,?,?)",
                    (f"{_fy}-{_period}", _w1s.isoformat(), _w1e.isoformat(),
                     _w2s.isoformat(), _w2e.isoformat())
                )
        _db.commit()

    from app.routes import auth, hours, forecast, admin, bulk
    app.register_blueprint(auth.bp)
    app.register_blueprint(hours.bp)
    app.register_blueprint(forecast.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(bulk.bp)

    @app.route('/')
    def index():
        return redirect(url_for('bulk.index'))

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('error.html', code=404, message='Page not found'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template('error.html', code=500, message='Server error'), 500

    return app
