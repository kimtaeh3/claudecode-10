from datetime import datetime, timedelta
import pandas
from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from app.routes.auth import login_required
from app.services.q360 import Q360Service, CATEGORIES, COMPANIES
from app.db import get_db

bp = Blueprint('hours', __name__, url_prefix='/hours')

def _svc():
    return Q360Service(session['user_id'], session['password'])


def _distinct_teams(db):
    """Return sorted unique individual team names from comma-separated team column."""
    rows = db.execute('SELECT team FROM team_member').fetchall()
    seen = set()
    for r in rows:
        for t in r['team'].split(','):
            t = t.strip()
            if t:
                seen.add(t)
    teams = sorted(seen)
    # Ensure "All" is first
    if 'All' in teams:
        teams = ['All'] + [t for t in teams if t != 'All']
    return teams


@bp.route('/')
@login_required
def view():
    db = get_db()
    teams = _distinct_teams(db)
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
        if team == 'All':
            members = db.execute('SELECT username FROM team_member').fetchall()
        else:
            members = db.execute(
                "SELECT username FROM team_member "
                "WHERE INSTR(',' || team || ',', ',' || ? || ',') > 0",
                (team,)).fetchall()
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

    # Persist fetched hours to DB for Forecast view
    try:
        db = get_db()
        db.execute('CREATE TABLE IF NOT EXISTS bulk_hours ('
                   'id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, '
                   'employee TEXT NOT NULL DEFAULT \'\', q360id TEXT NOT NULL DEFAULT \'\', '
                   'project TEXT NOT NULL DEFAULT \'\', category TEXT NOT NULL DEFAULT \'\', '
                   'company TEXT NOT NULL DEFAULT \'\', date TEXT NOT NULL, hours REAL NOT NULL, '
                   'submitted_at TEXT NOT NULL DEFAULT (datetime(\'now\',\'localtime\')), '
                   'timebillno TEXT)')
        for uid, data in results.items():
            uid_upper = uid.upper()
            db.execute('DELETE FROM bulk_hours WHERE username = ? AND date BETWEEN ? AND ?',
                       (uid_upper, start, end))
            for entry in data.get('userReport', []):
                date_val = (entry.get('startDate') or '')[:10]
                if not date_val:
                    continue
                db.execute(
                    'INSERT INTO bulk_hours (username, employee, q360id, project, category, company, date, hours) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (uid_upper, uid_upper, '', entry.get('project', ''), entry.get('category', ''),
                     entry.get('company', ''), date_val, float(entry.get('hours', 0)))
                )
        # Auto-add team members from Q360 results, but only if not already present.
        # Normalize: first letter + last word (uppercased) to catch middle-name variants.
        # e.g. 'bsree vathasavai' normalizes to 'BVATHASAVAI' — same as existing BVATHASAVAI.
        def _norm(u):
            parts = u.strip().split()
            if len(parts) <= 1:
                return u.upper()
            return (parts[0][0] + parts[-1]).upper()

        existing = db.execute('SELECT username FROM team_member').fetchall()
        existing_normalized = {_norm(r['username']) for r in existing}

        for uid, data in results.items():
            if not uid or len(uid) < 2 or not data.get('userReport'):
                continue
            uid_upper = uid.upper()
            if _norm(uid_upper) in existing_normalized:
                continue  # already exists (exact or middle-name variant)
            uid_name = ' '.join(p.capitalize() for p in uid_upper.lower().replace('.', ' ').replace('_', ' ').split())
            db.execute("INSERT INTO team_member (username, name, team) VALUES (?, ?, 'All')",
                       (uid_upper, uid_name))
            existing_normalized.add(uid_upper)  # prevent double-insert within same batch

        db.commit()
    except Exception:
        pass  # DB failure must not break the hours view

    return render_template('hours/_table.html', results=results)


@bp.route('/projects')
@login_required
def projects():
    # accept ?user= (lazy load) or ?target_user= (admin on-behalf)
    user_id = (request.args.get('target_user') or
               request.args.get('user') or
               session['user_id'])
    _NON_BILL_PREFIXES = (
        'ADMINISTRATION', 'ON-CALL', 'PERSONAL TIME-OFF', 'PERSONNAL TIME-OFF',
        'STATUTORY HOLIDAY', 'TRAINING', 'VACATION',
    )

    def _is_nonbill(desc):
        d = desc.upper()
        return any(d.startswith(p) for p in _NON_BILL_PREFIXES)

    try:
        svc = _svc()
        projects = svc.get_projects(user_id)
        # Load saved preferences for this user
        db = get_db()
        pref_rows = db.execute(
            'SELECT description, task_id FROM user_project_pref WHERE username = ?', (user_id,)
        ).fetchall()
        prefs = {row['description']: row['task_id'] for row in pref_rows}

        billable_by_desc = {}  # description → list of task_ids
        nonbill_best = {}      # normalized description → (rzk, desc)
        for k, v in projects.items():
            if Q360Service._is_admin_project(v.get('title', '')):
                continue
            desc = v.get('description', '').strip()
            if not desc:
                continue
            if _is_nonbill(desc):
                key = desc.upper().replace('PERSONNAL', 'PERSONAL')
                cur = nonbill_best.get(key)
                if cur is None or int(k) > int(cur[0]):
                    nonbill_best[key] = (k, desc)
            else:
                billable_by_desc.setdefault(desc, []).append(k)

        billable = []
        for desc, task_ids in billable_by_desc.items():
            pref_id = prefs.get(desc)
            if pref_id and pref_id in task_ids:
                chosen = pref_id
            else:
                chosen = task_ids[0]
            billable.append((desc, chosen))
        items = sorted(billable) + [(desc, rzk) for rzk, desc in nonbill_best.values()]
    except Exception:
        items = []
    return render_template('hours/_projects.html', items=items)


@bp.route('/projects/debug')
@login_required
def projects_debug():
    """Return raw Q360 project fields for a user — useful for comparing duplicate task IDs.
    Optional: ?user=username, ?ids=61082234,78910102 to filter to specific task IDs."""
    user_id = request.args.get('user') or session['user_id']
    filter_ids = set(request.args.get('ids', '').split(',')) - {''}
    try:
        svc = _svc()
        projects = svc.get_projects(user_id)
        FIELDS = ['description', 'title', 'projecttitle', 'opporno', 'projectno',
                  'company', 'sitecity', 'invoiceno', 'category']
        rows = []
        for rzk, item in sorted(projects.items(), key=lambda x: x[1].get('description', '')):
            if filter_ids and rzk not in filter_ids:
                continue
            row = {f: item.get(f, '') for f in FIELDS}
            row['resq_zoom_key'] = rzk
            rows.append(row)
        return jsonify(rows)
    except Exception as ex:
        return jsonify({'error': str(ex)}), 500


@bp.route('/submit', methods=['GET'])
@login_required
def submit():
    return render_template('hours/submit.html',
                           categories=CATEGORIES,
                           companies=COMPANIES,
                           is_admin=True)


@bp.route('/preview', methods=['POST'])
@login_required
def preview():
    f = request.form
    task_number = f.get('task_number', '')
    task_label = f.get('task_label', task_number)
    entry = f.get('entry', 'Single')
    mode = f.get('mode', 'time')
    note = f.get('note') or None
    company = f.get('company', 'CONNEX TELECOMMUNICATIONS INC.')
    include_weekends = f.get('weekends') == 'on'
    target_user = f.get('target_user') or session['user_id']
    category = f.get('category') or 'Auto (from task)'

    rows = []
    try:
        if mode == 'time':
            start_date = f['start_date']
            start_time = f['start_time']
            end_date = f['end_date'] if entry == 'Multiple' else start_date
            end_time = f['end_time']
            days = (pandas.date_range(start_date, end_date)
                    if include_weekends
                    else pandas.bdate_range(start_date, end_date, freq='B'))
            sd = datetime.strptime(f"{start_date} {start_time}", '%Y-%m-%d %H:%M')
            ed = datetime.strptime(f"{start_date} {end_time}", '%Y-%m-%d %H:%M')
            hours = (ed - sd).total_seconds() / 3600
            for day in days.strftime('%Y-%m-%d').tolist():
                rows.append({'date': day, 'start': start_time, 'end': end_time, 'hours': hours})
        else:
            start_date = f['start_date']
            end_date = f['end_date'] if entry == 'Multiple' else start_date
            start_time = f['start_time']
            hours_log = int(f.get('hours_log', 0))
            days = (pandas.date_range(start_date, end_date)
                    if include_weekends
                    else pandas.bdate_range(start_date, end_date, freq='B'))
            for day in days.strftime('%Y-%m-%d').tolist():
                rows.append({'date': day, 'start': start_time, 'end': '—', 'hours': hours_log})
    except Exception as e:
        return f'<div class="alert alert-danger">Preview error: {e}</div>'

    return render_template('hours/_preview.html',
                           rows=rows,
                           task_label=task_label,
                           task_number=task_number,
                           target_user=target_user,
                           category=category,
                           company=company,
                           note=note)


@bp.route('/submit', methods=['POST'])
@login_required
def submit_action():
    from flask import Response, stream_with_context
    return Response(
        stream_with_context(_submit_action_stream()),
        mimetype='text/event-stream',
        headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'},
    )


def _submit_action_stream():
    import json as _json
    import traceback

    def _evt(obj):
        return f'data: {_json.dumps(obj)}\n\n'

    f = request.form
    task_number = f.get('task_number', '')
    entry       = f.get('entry', 'Single')
    mode        = f.get('mode', 'time')
    note        = f.get('note') or None
    company     = f.get('company', 'CONNEX TELECOMMUNICATIONS INC.')
    include_weekends = f.get('weekends') == 'on'
    target_user = f.get('target_user') or None
    category    = f.get('category') or None

    svc = _svc()
    submitted = 0
    errors = []
    day_list = []

    try:
        if mode == 'time':
            start_date = f['start_date']
            start_time = f['start_time']
            end_date   = f['end_date']
            end_time   = f['end_time']
            days = (pandas.date_range(start_date, end_date) if include_weekends
                    else pandas.bdate_range(start_date, end_date, freq='B')) \
                   if entry == 'Multiple' else [start_date]
            day_list = list(days.strftime('%Y-%m-%d').tolist() if hasattr(days, 'strftime') else days)
        else:
            start_date = f['start_date']
            end_date   = f['end_date']
            start_time = f['start_time']
            hours_log  = int(f.get('hours_log', 0))
            days = (pandas.date_range(start_date, end_date) if include_weekends
                    else pandas.bdate_range(start_date, end_date, freq='B')) \
                   if entry == 'Multiple' else [start_date]
            day_list = list(days.strftime('%Y-%m-%d').tolist() if hasattr(days, 'strftime') else days)
    except Exception as ex:
        yield _evt({'type': 'error', 'html':
                    f'<div class="alert alert-danger">Input error: {ex}</div>'})
        return

    splits_per_day = 2 if (mode == 'hours' and hours_log > 4) else 1
    total = len(day_list) * splits_per_day
    yield _evt({'type': 'progress', 'done': 0, 'total': total,
                'msg': f'Submitting {total} entr\u00edy\u2026' if total == 1
                       else f'Submitting {total} entries\u2026'})

    try:
        for day in day_list:
            if mode == 'time':
                s  = f"{day}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
                e  = f"{day}%20{end_time[:2]}%3A{end_time[3:5]}%3A00.000"
                sd = datetime.strptime(f"{day} {start_time}", '%Y-%m-%d %H:%M')
                ed = datetime.strptime(f"{day} {end_time}",   '%Y-%m-%d %H:%M')
                delta = ed - sd
                log = f"{delta.total_seconds() / 3600:.2f}"
                svc.submit_hours(task_number, s, e, log, note, company, target_user, category)
                submitted += 1
                yield _evt({'type': 'progress', 'done': submitted, 'total': total,
                            'msg': f'Submitted \u2014 {day}'})
            else:
                end_h1 = str(int(start_time[:2]) + min(hours_log, 4))
                end_t1 = f"{end_h1}:{start_time[3:5]}"
                s1  = f"{day}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
                e1  = f"{day}%20{end_h1.zfill(2)}%3A{start_time[3:5]}%3A00.000"
                sd1 = datetime.strptime(f"{day} {start_time}", '%Y-%m-%d %H:%M')
                ed1 = datetime.strptime(f"{day} {end_t1}",     '%Y-%m-%d %H:%M')
                log1 = str(ed1 - sd1)[:-6] + '.' + str(ed1 - sd1)[-5:-3]
                svc.submit_hours(task_number, s1, e1, log1, note, company, target_user, category)
                submitted += 1
                yield _evt({'type': 'progress', 'done': submitted, 'total': total,
                            'msg': f'Submitted \u2014 {day}'})

                if hours_log > 4:
                    sh2 = str(int(start_time[:2]) + 5)
                    eh2 = str(int(start_time[:2]) + hours_log + 1)
                    et2 = f"{eh2}:{start_time[3:5]}"
                    s2  = f"{day}%20{sh2}%3A{start_time[3:5]}%3A00.000"
                    e2  = f"{day}%20{eh2.zfill(2)}%3A{start_time[3:5]}%3A00.000"
                    sd2 = datetime.strptime(f"{day} {sh2}:{start_time[3:5]}", '%Y-%m-%d %H:%M')
                    ed2 = datetime.strptime(f"{day} {et2}",                   '%Y-%m-%d %H:%M')
                    log2 = str(ed2 - sd2)[:-6] + '.' + str(ed2 - sd2)[-5:-3]
                    svc.submit_hours(task_number, s2, e2, log2, note, company, target_user, category)
                    submitted += 1
                    yield _evt({'type': 'progress', 'done': submitted, 'total': total,
                                'msg': f'Submitted \u2014 {day} (split 2)'})
    except Exception:
        errors.append(traceback.format_exc())

    try:
        html = render_template('hours/_submit_result.html', submitted=submitted, errors=errors)
        yield _evt({'type': 'complete', 'html': html})
    except Exception as ex:
        yield _evt({'type': 'error', 'html':
                    f'<div class="alert alert-danger">Render error: {ex}</div>'})
