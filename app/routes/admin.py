from flask import Blueprint, render_template, request, redirect, url_for
from app.routes.auth import login_required
from app.db import get_db

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/users')
@login_required
def users():
    db = get_db()
    members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
    teams = [r['team'] for r in db.execute(
        'SELECT DISTINCT team FROM team_member ORDER BY team').fetchall()]
    return render_template('admin/users.html', members=members, teams=teams)


@bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    username = request.form['username'].strip()
    team = request.form['team'].strip()
    email = request.form.get('email', '').strip()
    db = get_db()
    if not username or not team:
        if request.headers.get('HX-Request'):
            members = db.execute('SELECT * FROM team_member ORDER BY team, username').fetchall()
            return render_template('admin/_members_table.html', members=members,
                                   error='Username and team are required.')
        return redirect(url_for('admin.users'))
    try:
        db.execute('INSERT INTO team_member (username, team, email) VALUES (?, ?, ?)',
                   (username, team, email or None))
        db.commit()
    except Exception:
        pass  # duplicate username — silently ignore
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
