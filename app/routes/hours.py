from datetime import datetime, timedelta
import pandas
from flask import Blueprint, render_template, request, session, redirect, url_for
from app.routes.auth import login_required
from app.services.q360 import Q360Service, CATEGORIES, COMPANIES
from app.db import get_db

bp = Blueprint('hours', __name__, url_prefix='/hours')

def _svc():
    return Q360Service(session['user_id'], session['password'])


@bp.route('/')
@login_required
def view():
    db = get_db()
    teams = [r['team'] for r in db.execute(
        'SELECT DISTINCT team FROM team_member ORDER BY team').fetchall()]
    return render_template('hours/view.html', teams=teams)


@bp.route('/table')
@login_required
def table():
    user_id = request.args.get('user', '').strip()
    team = request.args.get('team', '')
    start = request.args.get('start', '')
    end = request.args.get('end', '')

    if not start or not end:
        return '<p class="text-muted">Select a date range and click Search.</p>'

    svc = _svc()
    results = {}

    if team and team != 'Single':
        db = get_db()
        members = db.execute(
            'SELECT username FROM team_member WHERE team = ?', (team,)).fetchall()
        for m in members:
            try:
                results[m['username']] = svc.get_hours(m['username'], start, end)
            except Exception:
                pass
    elif user_id:
        try:
            results[user_id] = svc.get_hours(user_id, start, end)
        except Exception as e:
            return f'<div class="alert alert-danger">Error: {e}</div>'
    else:
        return '<p class="text-muted">Enter a user ID or select a team.</p>'

    return render_template('hours/_table.html', results=results)


@bp.route('/projects')
@login_required
def projects():
    # accept ?user= (lazy load) or ?target_user= (admin on-behalf)
    user_id = (request.args.get('target_user') or
               request.args.get('user') or
               session['user_id'])
    try:
        svc = _svc()
        projects = svc.get_projects(user_id)
        items = [
            (v['description'], k) for k, v in projects.items()
            if not Q360Service._is_admin_project(v.get('title', ''))
            and v.get('description', '').strip()
        ]
    except Exception:
        items = []
    return render_template('hours/_projects.html', items=items)


@bp.route('/submit', methods=['GET'])
@login_required
def submit():
    return render_template('hours/submit.html',
                           categories=CATEGORIES,
                           companies=COMPANIES,
                           is_admin=True)


@bp.route('/submit', methods=['POST'])
@login_required
def submit_action():
    f = request.form
    task_number = f.get('task_number', '')
    entry = f.get('entry', 'Single')
    mode = f.get('mode', 'time')  # 'time' or 'hours'
    note = f.get('note', 'POWERED BY Q360 AUTO APP')
    company = f.get('company', 'CONNEX TELECOMMUNICATIONS INC.')
    include_weekends = f.get('weekends') == 'on'
    target_user = f.get('target_user') or None
    category = f.get('category') or None

    svc = _svc()
    submitted = 0
    errors = []

    try:
        if mode == 'time':
            start_date = f['start_date']
            start_time = f['start_time']
            end_date = f['end_date']
            end_time = f['end_time']

            if entry == 'Multiple':
                days = (pandas.date_range(start_date, end_date)
                        if include_weekends
                        else pandas.bdate_range(start_date, end_date, freq='B'))
                day_list = days.strftime('%Y-%m-%d').tolist()
            else:
                day_list = [start_date]

            for day in day_list:
                s = f"{day}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
                e = f"{day}%20{end_time[:2]}%3A{end_time[3:5]}%3A00.000"
                sd = datetime.strptime(f"{day} {start_time}", '%Y-%m-%d %H:%M')
                ed = datetime.strptime(f"{day} {end_time}", '%Y-%m-%d %H:%M')
                delta = ed - sd
                log = f"{str(delta)[:-6]}.{str(delta)[-5:-3]}"
                svc.submit_hours(task_number, s, e, log, note, company, target_user, category)
                submitted += 1

        else:  # hours mode
            start_date = f['start_date']
            end_date = f['end_date']
            start_time = f['start_time']
            hours_log = int(f.get('hours_log', 0))

            if entry == 'Multiple':
                days = (pandas.date_range(start_date, end_date)
                        if include_weekends
                        else pandas.bdate_range(start_date, end_date, freq='B'))
                day_list = days.strftime('%Y-%m-%d').tolist()
            else:
                day_list = [start_date]

            for day in day_list:
                end_h1 = str(int(start_time[:2]) + min(hours_log, 4))
                end_t1 = f"{end_h1}:{start_time[3:5]}"
                s1 = f"{day}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
                e1 = f"{day}%20{end_h1.zfill(2)}%3A{start_time[3:5]}%3A00.000"
                sd1 = datetime.strptime(f"{day} {start_time}", '%Y-%m-%d %H:%M')
                ed1 = datetime.strptime(f"{day} {end_t1}", '%Y-%m-%d %H:%M')
                log1 = str(ed1 - sd1)[:-6] + '.' + str(ed1 - sd1)[-5:-3]
                svc.submit_hours(task_number, s1, e1, log1, note, company, target_user, category)
                submitted += 1

                if hours_log > 4:
                    sh2 = str(int(start_time[:2]) + 5)
                    eh2 = str(int(start_time[:2]) + hours_log + 1)
                    et2 = f"{eh2}:{start_time[3:5]}"
                    s2 = f"{day}%20{sh2}%3A{start_time[3:5]}%3A00.000"
                    e2 = f"{day}%20{eh2.zfill(2)}%3A{start_time[3:5]}%3A00.000"
                    sd2 = datetime.strptime(f"{day} {sh2}:{start_time[3:5]}", '%Y-%m-%d %H:%M')
                    ed2 = datetime.strptime(f"{day} {et2}", '%Y-%m-%d %H:%M')
                    log2 = str(ed2 - sd2)[:-6] + '.' + str(ed2 - sd2)[-5:-3]
                    svc.submit_hours(task_number, s2, e2, log2, note, company, target_user, category)
                    submitted += 1

    except Exception as ex:
        errors.append(str(ex))

    return render_template('hours/_submit_result.html', submitted=submitted, errors=errors)
