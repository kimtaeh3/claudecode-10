from flask import Blueprint, render_template, request, session, redirect, url_for
from app.services.q360 import Q360Service
from app.db import get_db

bp = Blueprint('auth', __name__)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('bulk.index'))
    error = None
    if request.method == 'POST':
        user_id = request.form['user_id'].strip()
        password = request.form['password']
        try:
            svc = Q360Service(user_id, password)
            data = svc.login()
            if data.get('success'):
                session.clear()
                session['user_id'] = user_id
                session['password'] = password
                db = get_db()
                db.execute(
                    'INSERT INTO login_log (username, ip_address) VALUES (?, ?)',
                    (user_id, request.remote_addr)
                )
                db.commit()
                return redirect(url_for('bulk.index'))
            else:
                error = 'Invalid credentials. Please try again.'
        except Exception:
            error = 'Could not reach Q360. Check your connection.'
    return render_template('login.html', error=error)


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
