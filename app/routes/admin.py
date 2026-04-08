import json as _json
from collections import defaultdict
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from app.routes.auth import login_required
from app.routes.forecast import ontario_holidays_named
from app.db import get_db

bp = Blueprint('admin', __name__, url_prefix='/admin')


def _member_stats(db):
    rows = db.execute(
        'SELECT username, MAX(submitted_at) as last_updated, '
        'MIN(date) as date_min, MAX(date) as date_max '
        'FROM bulk_hours GROUP BY username'
    ).fetchall()
    return {r['username']: r for r in rows}


def _contractor_allocs(db):
    """Return dict: member_id → list of {project_name, utilization_pct}"""
    try:
        rows = db.execute(
            'SELECT member_id, project_name, utilization_pct, start_date, end_date '
            'FROM contractor_allocation ORDER BY id'
        ).fetchall()
    except Exception:
        return {}
    allocs = defaultdict(list)
    for r in rows:
        allocs[r['member_id']].append({
            'project_name': r['project_name'],
            'utilization_pct': r['utilization_pct'],
            'start_date': r['start_date'] or '',
            'end_date': r['end_date'] or '',
        })
    return dict(allocs)


@bp.route('/users')
@login_required
def users():
    db = get_db()
    members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
    seen = set()
    for m in members:
        for t in m['team'].split(','):
            t = t.strip()
            if t:
                seen.add(t)
    teams = ['All'] + sorted(t for t in seen if t != 'All')

    return render_template('admin/users.html', members=members, teams=teams,
                           member_stats=_member_stats(db),
                           contractor_allocs=_contractor_allocs(db))


def _build_name(first, middle, last):
    parts = [p for p in [first, middle, last] if p]
    return ' '.join(parts)


@bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    username = request.form['username'].strip().upper()
    first_name  = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    last_name   = request.form.get('last_name', '').strip()
    name = _build_name(first_name, middle_name, last_name)
    team = request.form['team'].strip()
    email = request.form.get('email', '').strip()
    member_type = request.form.get('member_type', 'Employee (100%)').strip()
    db = get_db()
    if not username or not team:
        if request.headers.get('HX-Request'):
            members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
            return render_template('admin/_members_table.html', members=members,
                                   member_stats=_member_stats(db),
                                   error='Username and team are required.')
        return redirect(url_for('admin.users'))
    existing = db.execute(
        'SELECT id, username, name FROM team_member '
        'WHERE username = ? OR (name != "" AND LOWER(name) = LOWER(?))',
        (username, name)
    ).fetchone()
    if existing:
        if existing['username'].upper() == username:
            return ('Username already exists', 409)
        return (f'Name already exists (as {existing["username"]})', 409)
    db.execute(
        'INSERT INTO team_member (username, first_name, middle_name, last_name, name, team, email, member_type) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (username, first_name, middle_name, last_name, name, team, email or None, member_type))
    db.commit()
    if request.headers.get('HX-Request'):
        members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
        return render_template('admin/_members_table.html', members=members,
                               member_stats=_member_stats(db),
                               contractor_allocs=_contractor_allocs(db))
    return redirect(url_for('admin.users'))


@bp.route('/users/edit/<int:member_id>', methods=['POST'])
@login_required
def edit_user(member_id):
    username    = request.form.get('username', '').strip().upper()
    first_name  = request.form.get('first_name', '').strip()
    middle_name = request.form.get('middle_name', '').strip()
    last_name   = request.form.get('last_name', '').strip()
    name        = _build_name(first_name, middle_name, last_name)
    team        = request.form.get('team', '').strip()
    email       = request.form.get('email', '').strip()
    member_type = request.form.get('member_type', 'Employee (100%)').strip()
    start_date  = request.form.get('start_date', '').strip() or None
    end_date    = request.form.get('end_date', '').strip() or None
    notes       = request.form.get('notes', '').strip() or None
    db = get_db()
    if username and team:
        db.execute(
            'UPDATE team_member SET username=?, first_name=?, middle_name=?, last_name=?, name=?, '
            'team=?, email=?, member_type=?, start_date=?, end_date=?, notes=? WHERE id=?',
            (username, first_name, middle_name, last_name, name,
             team, email or None, member_type, start_date, end_date, notes, member_id))
        # Save contractor allocations
        try:
            db.execute('DELETE FROM contractor_allocation WHERE member_id = ?', (member_id,))
            raw = request.form.get('contractor_projects', '[]')
            for cp in _json.loads(raw):
                pname = str(cp.get('project_name', '')).strip()
                pct = float(cp.get('utilization_pct', 0))
                if pname and pct > 0:
                    sd = str(cp.get('start_date', '') or '').strip() or None
                    ed = str(cp.get('end_date', '') or '').strip() or None
                    db.execute(
                        'INSERT INTO contractor_allocation (member_id, project_name, utilization_pct, start_date, end_date) VALUES (?, ?, ?, ?, ?)',
                        (member_id, pname, pct, sd, ed))
        except Exception:
            pass
        db.commit()
    if request.headers.get('HX-Request'):
        members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
        return render_template('admin/_members_table.html', members=members,
                               member_stats=_member_stats(db),
                               contractor_allocs=_contractor_allocs(db))
    return redirect(url_for('admin.users'))


@bp.route('/users/delete/<int:member_id>', methods=['DELETE', 'POST'])
@login_required
def delete_user(member_id):
    db = get_db()
    db.execute('DELETE FROM team_member WHERE id = ?', (member_id,))
    db.commit()
    if request.headers.get('HX-Request'):
        members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
        return render_template('admin/_members_table.html', members=members,
                               member_stats=_member_stats(db),
                               contractor_allocs=_contractor_allocs(db))
    return redirect(url_for('admin.users'))


@bp.route('/projects')
@login_required
def projects():
    db = get_db()
    entries = db.execute('SELECT * FROM nonbillable_project ORDER BY name').fetchall()
    return render_template('admin/projects.html', entries=entries)


@bp.route('/projects/add', methods=['POST'])
@login_required
def add_project():
    name = request.form.get('name', '').strip()
    db = get_db()
    if name:
        try:
            db.execute('INSERT INTO nonbillable_project (name) VALUES (?)', (name,))
            db.commit()
        except Exception:
            pass  # duplicate
    entries = db.execute('SELECT * FROM nonbillable_project ORDER BY name').fetchall()
    return render_template('admin/_projects_table.html', entries=entries)


@bp.route('/projects/delete/<int:entry_id>', methods=['DELETE', 'POST'])
@login_required
def delete_project(entry_id):
    db = get_db()
    db.execute('DELETE FROM nonbillable_project WHERE id = ?', (entry_id,))
    db.commit()
    entries = db.execute('SELECT * FROM nonbillable_project ORDER BY name').fetchall()
    return render_template('admin/_projects_table.html', entries=entries)


@bp.route('/holidays')
@login_required
def holidays():
    year = request.args.get('year', type=int, default=date.today().year)
    hols = ontario_holidays_named(year)
    years = list(range(date.today().year - 2, date.today().year + 3))
    return render_template('admin/holidays.html', holidays=hols, year=year, years=years)
