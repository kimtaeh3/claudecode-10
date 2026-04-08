import sqlite3
import click
from flask import current_app, g


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf-8'))
    # Migrate existing team_member table: add first/middle/last name columns if absent
    for col in ('first_name', 'middle_name', 'last_name'):
        try:
            db.execute(f"ALTER TABLE team_member ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            db.commit()
        except Exception:
            pass  # column already exists

    # Backfill first/middle/last from existing name where not yet split
    rows = db.execute(
        "SELECT id, name FROM team_member WHERE name != '' AND first_name = '' AND last_name = ''"
    ).fetchall()
    for row in rows:
        parts = row['name'].strip().split()
        if len(parts) == 1:
            first, middle, last = parts[0], '', ''
        elif len(parts) == 2:
            first, middle, last = parts[0], '', parts[1]
        else:
            first, middle, last = parts[0], ' '.join(parts[1:-1]), parts[-1]
        db.execute(
            "UPDATE team_member SET first_name=?, middle_name=?, last_name=? WHERE id=?",
            (first, middle, last, row['id'])
        )
    if rows:
        db.commit()


@click.command('init-db')
def init_db_command():
    init_db()
    click.echo('Database initialised.')


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
