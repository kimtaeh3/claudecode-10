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
        # Default non-billable project pattern
        _db.execute(
            "INSERT OR IGNORE INTO nonbillable_project (name) VALUES ('INTERNAL CONNEX')"
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
