from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from app.routes.auth import login_required
from app.routes.forecast import ontario_holidays_named
from app.db import get_db

bp = Blueprint('admin', __name__, url_prefix='/admin')


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
    return render_template('admin/users.html', members=members, teams=teams)


@bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    username = request.form['username'].strip()
    name = request.form.get('name', '').strip()
    team = request.form['team'].strip()
    email = request.form.get('email', '').strip()
    member_type = request.form.get('member_type', 'Employee (100%)').strip()
    db = get_db()
    if not username or not team:
        if request.headers.get('HX-Request'):
            members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
            return render_template('admin/_members_table.html', members=members,
                                   error='Username and team are required.')
        return redirect(url_for('admin.users'))
    existing = db.execute('SELECT id FROM team_member WHERE username = ?', (username,)).fetchone()
    if existing:
        return ('Username already exists', 409)
    db.execute('INSERT INTO team_member (username, name, team, email, member_type) VALUES (?, ?, ?, ?, ?)',
               (username, name, team, email or None, member_type))
    db.commit()
    if request.headers.get('HX-Request'):
        members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
        return render_template('admin/_members_table.html', members=members)
    return redirect(url_for('admin.users'))


@bp.route('/users/edit/<int:member_id>', methods=['POST'])
@login_required
def edit_user(member_id):
    username = request.form.get('username', '').strip()
    name = request.form.get('name', '').strip()
    team = request.form.get('team', '').strip()
    email = request.form.get('email', '').strip()
    member_type = request.form.get('member_type', 'Employee (100%)').strip()
    db = get_db()
    if username and team:
        db.execute('UPDATE team_member SET username=?, name=?, team=?, email=?, member_type=? WHERE id=?',
                   (username, name, team, email or None, member_type, member_id))
        db.commit()
    if request.headers.get('HX-Request'):
        members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
        return render_template('admin/_members_table.html', members=members)
    return redirect(url_for('admin.users'))


@bp.route('/users/delete/<int:member_id>', methods=['DELETE', 'POST'])
@login_required
def delete_user(member_id):
    db = get_db()
    db.execute('DELETE FROM team_member WHERE id = ?', (member_id,))
    db.commit()
    if request.headers.get('HX-Request'):
        members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
        return render_template('admin/_members_table.html', members=members)
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
