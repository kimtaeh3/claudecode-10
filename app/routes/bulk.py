import json
from datetime import datetime, timedelta

import pandas as pd
from flask import Blueprint, render_template, request, session

from app.routes.auth import login_required
from app.services.q360 import Q360Service, CATEGORIES, COMPANIES
from app.db import get_db

bp = Blueprint('bulk', __name__, url_prefix='/bulk')

DAY_COLS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
DAY_OFFSETS = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6}
DEFAULT_CATEGORY = 'VOICE- CCAPPDEV'
DEFAULT_COMPANY = 'CONNEX TELECOMMUNICATIONS INC.'


def _svc():
    return Q360Service(session['user_id'], session['password'])


def _fmt_time(dt):
    """Format datetime as HH:MM string."""
    return dt.strftime('%H:%M')


def _week_monday(excel_week):
    """Convert Excel week (0-51) to its Monday. Week 0 = Mon of ISO week 52 of previous year."""
    year = datetime.now().year
    week_0_monday = datetime.fromisocalendar(year - 1, 52, 1)
    return week_0_monday + timedelta(weeks=int(excel_week))


def _normalize(s):
    return s.lower().strip() if s else ''


def _build_recommendations(task_rows):
    """For task rows missing Q360ID, recommend from earlier weeks by customer+project similarity."""
    from collections import defaultdict

    by_cust_proj = defaultdict(lambda: defaultdict(set))
    by_cust      = defaultdict(lambda: defaultdict(set))
    by_user      = defaultdict(lambda: defaultdict(set))
    # Track best (customer, project) seen for each (username, q360id) — most recent week wins
    q360_details = {}  # (username, q360id) -> (customer, project, week)

    for r in task_rows:
        if not r['needs_attention'] and r['q360id']:
            u, ck, pk, wk = r['username'], _normalize(r['customer']), _normalize(r['project']), r['week_num']
            by_cust_proj[(u, ck, pk)][wk].add(r['q360id'])
            by_cust[(u, ck)][wk].add(r['q360id'])
            by_user[u][wk].add(r['q360id'])
            if r['customer']:  # only index rows with actual project data
                key = (u, r['q360id'])
                if key not in q360_details or q360_details[key][2] < wk:
                    q360_details[key] = (r['customer'], r['project'], wk)

    def _collect(mapping, key, max_week):
        ids = set()
        for wk, qids in mapping.get(key, {}).items():
            if wk < max_week:
                ids.update(qids)
        return ids

    for r in task_rows:
        if not r['needs_attention']:
            r['recommended_q360ids'] = []
            r['suggested'] = False
            continue
        u, ck, pk, wk = r['username'], _normalize(r['customer']), _normalize(r['project']), r['week_num']
        candidates = _collect(by_cust_proj, (u, ck, pk), wk)
        if not candidates:
            candidates = _collect(by_cust, (u, ck), wk)
        if not candidates:
            candidates = _collect(by_user, u, wk)
        r['recommended_q360ids'] = sorted(candidates)
        # Auto-apply single match
        if len(candidates) == 1:
            qid = sorted(candidates)[0]
            r['q360id'] = qid
            r['suggested'] = True
            r['needs_attention'] = False
            # Also fill customer/project if missing
            if not r['customer'] and not r['project']:
                details = q360_details.get((u, qid))
                if details:
                    r['customer']       = details[0]
                    r['project']        = details[1]
                    r['project_guessed'] = True
        else:
            r['suggested'] = False

    # Third pass: fill missing customer/project for any row that has a q360id but blank customer
    for r in task_rows:
        if r['q360id'] and not r['customer'] and not r['project']:
            details = q360_details.get((r['username'], r['q360id']))
            if details:
                r['customer']        = details[0]
                r['project']         = details[1]
                r['project_guessed'] = True


def _assign_time_slots(task_rows):
    """Assign non-overlapping start/end times per (username, day), ordered by row_num."""
    from collections import defaultdict
    # Build per (username, date) ordered list of (row, day) with hours
    slots = defaultdict(list)
    for r in task_rows:
        for day, d in r['days'].items():
            if d['hours'] > 0:
                slots[(r['username'], d['date'])].append((r['row_num'], r, day))

    for entries in slots.values():
        entries.sort(key=lambda x: x[0])
        current = datetime.strptime(entries[0][1]['days'][entries[0][2]]['date'] + ' 08:00',
                                    '%Y-%m-%d %H:%M')
        for _, r, day in entries:
            d = r['days'][day]
            d['start_time'] = _fmt_time(current)
            current_end = current + timedelta(hours=d['hours'])
            d['end_time'] = _fmt_time(current_end)
            current = current_end


def _fill_missing_weeks(task_rows):
    """For weeks present for some users but not others, synthesize rows from nearest week."""
    from collections import defaultdict

    all_weeks = sorted(set(r['week_num'] for r in task_rows))
    if len(all_weeks) <= 1:
        return []

    by_user = defaultdict(list)
    for r in task_rows:
        by_user[r['username']].append(r)

    max_row_num = max(r['row_num'] for r in task_rows)
    new_rows = []

    for username, rows in by_user.items():
        user_weeks = sorted(set(r['week_num'] for r in rows))
        for week_num in all_weeks:
            if week_num in user_weeks:
                continue

            # Find closest week (prefer previous, fall back to next)
            prev = [w for w in user_weeks if w < week_num]
            nxt  = [w for w in user_weeks if w > week_num]
            source_week = prev[-1] if prev else (nxt[0] if nxt else None)
            if source_week is None:
                continue

            source_rows = [r for r in rows if r['week_num'] == source_week]
            week_start = _week_monday(week_num)
            week_end   = week_start + timedelta(days=4)
            week_range = (f"Wk {week_num}: "
                          f"{week_start.strftime('%b')} {week_start.day}–{week_end.day}, {week_start.year}")

            for src in source_rows:
                max_row_num += 1
                new_days = {}
                for day in DAY_COLS:
                    date = (week_start + timedelta(days=DAY_OFFSETS[day])).strftime('%Y-%m-%d')
                    new_days[day] = {
                        'hours': src['days'][day]['hours'],
                        'date': date,
                        'start_time': '',
                        'end_time': '',
                    }
                new_rows.append({
                    'row_num':            max_row_num,
                    'week_num':           week_num,
                    'week_range':         week_range,
                    'username':           username,
                    'employee':           src['employee'],
                    'customer':           src['customer'],
                    'project':            src['project'],
                    'q360id':             src['q360id'],
                    'needs_attention':    src['needs_attention'],
                    'suggested':          src['suggested'],
                    'category':           src['category'],
                    'company':            src['company'],
                    'comment':            src['comment'],
                    'days':               new_days,
                    'recommended_q360ids': list(src.get('recommended_q360ids', [])),
                    'missing_week':       True,
                    'missing_guessed_from': source_week,
                })
    return new_rows


def _apply_username_corrections(grouped):
    """Replace Excel-derived usernames with saved Q360 corrections from the DB."""
    rows = get_db().execute('SELECT employee_name, q360_username FROM username_map').fetchall()
    corrections = {r['employee_name']: r['q360_username'] for r in rows}
    if not corrections:
        return grouped
    for u in grouped:
        corrected = corrections.get(u['employee'])
        if corrected:
            u['username'] = corrected
            for r in u['rows']:
                r['username'] = corrected
    return grouped


def _filter_by_date(grouped, mode):
    """Filter grouped rows to only those whose week overlaps the selected date range.
    A week overlaps a range when: week_monday <= range_end AND week_sunday >= range_start.
    Full weeks are always kept intact even if they straddle a month/year boundary.
    """
    if mode == 'all':
        return grouped
    import calendar as _cal
    today = datetime.today().date()

    if mode == 'week':
        range_start = today - timedelta(days=today.weekday())
        range_end   = range_start + timedelta(days=6)
    elif mode == 'month':
        range_start = today.replace(day=1)
        range_end   = today.replace(day=_cal.monthrange(today.year, today.month)[1])
    elif mode == 'year':
        range_start = today.replace(month=1, day=1)
        range_end   = today.replace(month=12, day=31)
    else:
        return grouped

    result = []
    for u in grouped:
        filtered = []
        for r in u['rows']:
            monday = _week_monday(r['week_num']).date()
            sunday = monday + timedelta(days=6)
            # Overlap: week touches the range at all
            if monday <= range_end and sunday >= range_start:
                filtered.append(r)
        if filtered:
            result.append({**u, 'rows': filtered})
    return result


def _parse_excel(file):
    """Parse uploaded Excel file. Returns list of user dicts, each with task rows."""
    filename = file.filename.lower()
    if filename.endswith('.xlsb'):
        df = pd.read_excel(file, engine='pyxlsb', sheet_name=0)
    else:
        df = pd.read_excel(file, engine='openpyxl', sheet_name=0)

    from collections import defaultdict

    task_rows = []
    row_num = 0

    for _, row in df.iterrows():
        username = str(row.get('Username', '') or '').strip()
        employee = str(row.get('Employee', '') or '').strip()
        if not username or username == 'nan':
            # Derive username from Employee full name: first letter + last name
            if employee and employee != 'nan':
                parts = employee.strip().split()
                if len(parts) >= 2:
                    username = (parts[0][0] + parts[-1]).lower()
                else:
                    continue
            else:
                continue

        week_val = row.get('Week')
        if week_val is None or str(week_val) == 'nan':
            continue
        week_num = int(float(week_val))
        week_start = _week_monday(week_num)

        def _clean(v):
            s = str(v or '').strip()
            return '' if s == 'nan' else s

        customer = _clean(row.get('Customer', ''))
        project  = _clean(row.get('Project', ''))
        comment  = _clean(row.get('Comment', ''))


        # Build per-day data (all days, 0 if no hours)
        days = {}
        has_any = False
        for day in DAY_COLS:
            h = row.get(day)
            hours = 0.0 if (h is None or str(h) == 'nan') else float(h)
            date = (week_start + timedelta(days=DAY_OFFSETS[day])).strftime('%Y-%m-%d')
            days[day] = {'hours': hours, 'date': date, 'start_time': '', 'end_time': ''}
            if hours > 0:
                has_any = True

        if not has_any:
            continue

        week_end = week_start + timedelta(days=4)
        week_range = (f"Wk {week_num}: "
                      f"{week_start.strftime('%b')} {week_start.day}–{week_end.day}, {week_start.year}")

        row_num += 1
        task_rows.append({
            'row_num': row_num,
            'week_num': week_num,
            'week_range': week_range,
            'username': username,
            'employee': employee,
            'customer': customer,
            'project': project,
            'q360id': '',
            'needs_attention': True,
            'suggested': False,
            'category': '',
            'company': DEFAULT_COMPANY,
            'comment': comment,
            'days': days,
            'recommended_q360ids': [],
            'missing_week': False,
            'missing_guessed_from': None,
            'project_guessed': False,
        })

    _build_recommendations(task_rows)

    # Fill missing weeks before assigning time slots so slots cover synthetic rows too
    missing = _fill_missing_weeks(task_rows)
    task_rows.extend(missing)
    task_rows.sort(key=lambda r: (r['username'], r['week_num'], r['row_num']))

    _assign_time_slots(task_rows)

    # Group by user, preserving order of first appearance
    seen_users = []
    by_user_map = {}
    for r in task_rows:
        u = r['username']
        if u not in by_user_map:
            seen_users.append(u)
            by_user_map[u] = []
        by_user_map[u].append(r)

    return [{'username': u, 'employee': by_user_map[u][0]['employee'], 'rows': by_user_map[u]}
            for u in seen_users]


@bp.route('/')
@login_required
def index():
    return render_template('bulk/index.html')


@bp.route('/parse', methods=['POST'])
@login_required
def parse():
    import traceback as _tb
    file = request.files.get('file')
    if not file:
        return '<div class="alert alert-danger">Please provide a file.</div>'
    date_filter = request.form.get('date_filter', 'month')
    try:
        grouped = _parse_excel(file)
    except Exception as e:
        return f'<div class="alert alert-danger">Failed to parse file: {e}</div>'
    grouped = _apply_username_corrections(grouped)
    grouped = _filter_by_date(grouped, date_filter)
    if not grouped:
        return '<div class="alert alert-warning">No entries found for the selected date range.</div>'
    try:
        return _do_parse(grouped)
    except Exception:
        return (f'<div class="alert alert-danger"><strong>Unexpected error — please report:'
                f'</strong><pre style="font-size:.75rem;white-space:pre-wrap">'
                f'{_tb.format_exc()}</pre></div>')


def _do_parse(grouped):
    import re as _re
    # Determine which day columns have any data
    active_days = [d for d in DAY_COLS if any(
        r['days'][d]['hours'] > 0 for u in grouped for r in u['rows']
    )]

    # Fetch live Q360 projects per user and guess resq_zoom_key from Excel Project column.
    # Wrapped in try/except so any API or matching failure falls back gracefully.

    def _match_score(excel_customer, excel_project, q360_desc):
        search = ' '.join(filter(None, [excel_customer, excel_project])).lower()
        desc = q360_desc.lower()
        search = _re.sub(r'[^\w\s]', ' ', search)
        desc   = _re.sub(r'[^\w\s]', ' ', desc)
        words = [w for w in search.split() if len(w) > 2]
        if not words:
            return 0.0
        return sum(1 for w in words if w in desc) / len(words)

    try:
        svc = _svc()
        live_by_user = {}
        for u in grouped:
            try:
                live_by_user[u['username']] = svc.get_projects(u['username'])
            except Exception:
                live_by_user[u['username']] = {}

        # Guess resq_zoom_key for each row by text-matching Excel Project → Q360 description
        for u in grouped:
            live = live_by_user.get(u['username'], {})
            if not live:
                continue
            for r in u['rows']:
                qid = r.get('q360id', '')
                if qid and qid in live:
                    desc = live[qid].get('description', '').strip()
                    if desc:
                        r['customer'] = desc
                    continue
                best_rzk, best_score, first_rzk = None, 0.0, None
                for rzk, item in live.items():
                    if Q360Service._is_admin_project(item.get('title', '')):
                        continue
                    if first_rzk is None:
                        first_rzk = rzk
                    score = _match_score(r.get('customer', ''), r.get('project', ''),
                                         item.get('description', ''))
                    if score > best_score:
                        best_score, best_rzk = score, rzk
                # Always pick best match (or first project if no text match)
                chosen = best_rzk or first_rzk
                if chosen:
                    item = live[chosen]
                    r['q360id']          = chosen
                    r['customer']        = item.get('description', '').strip()
                    r['category']        = item.get('category', '') or DEFAULT_CATEGORY
                    r['needs_attention'] = False
                    r['project_guessed'] = True
                    r['suggested']       = True

        # Build dropdown options from live Q360 data (resq_zoom_key as q360id)
        user_projects = {}
        for u in grouped:
            live = live_by_user.get(u['username'], {})
            combos = []
            for rzk, item in live.items():
                if Q360Service._is_admin_project(item.get('title', '')):
                    continue
                desc = item.get('description', '').strip()
                if not desc:
                    continue
                cat = item.get('category', DEFAULT_CATEGORY) or DEFAULT_CATEGORY
                combos.append({'customer': desc, 'project': '', 'q360id': rzk, 'category': cat})
            user_projects[u['username']] = combos

    except Exception:
        # Fall back: build user_projects from Excel data so the table still renders
        user_projects = {}
        for u in grouped:
            combos = []
            seen_keys = set()
            for r in u['rows']:
                if not r['needs_attention'] and r['customer']:
                    key = (r['customer'], r['project'], r['q360id'])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        combos.append({'customer': r['customer'], 'project': r['project'],
                                       'q360id': r['q360id'], 'category': r['category']})
            user_projects[u['username']] = combos

    all_weeks = sorted(set(r['week_num'] for u in grouped for r in u['rows']))
    week_mondays = {w: _week_monday(w).strftime('%Y-%m-%d') for w in all_weeks}
    # Compute current Excel week number using the same logic as _week_monday
    _today = datetime.today().date()
    _year = _today.year
    _week0 = datetime.fromisocalendar(_year - 1, 52, 1).date()
    current_week_num = (_today - _week0).days // 7
    return render_template('bulk/_table.html', grouped=grouped, categories=CATEGORIES,
                           default_category=DEFAULT_CATEGORY, active_days=active_days,
                           user_projects=user_projects,
                           all_weeks=all_weeks, week_mondays=week_mondays,
                           current_week_num=current_week_num)


@bp.route('/review', methods=['POST'])
@login_required
def review():
    entries_json = request.form.get('entries', '[]')
    try:
        entries = json.loads(entries_json)
    except Exception:
        return '<div class="alert alert-danger">Invalid submission data.</div>'

    # Collect date ranges per user so we can check what's already in the system
    from collections import defaultdict
    user_dates = defaultdict(set)
    for e in entries:
        if e.get('q360id'):
            for d in e.get('days', []):
                if d.get('date'):
                    user_dates[e['username']].add(d['date'])

    # Fetch existing timebills for each user/range
    existing = {}  # "username|date" -> total hours already logged
    api_errors = {}  # username -> error message
    svc = _svc()
    for username, dates in user_dates.items():
        if not dates:
            continue
        # Pre-mark all dates as clear (0h); overwritten if timebills are found
        for d in dates:
            existing[f"{username}|{d}"] = 0.0
        try:
            result = svc.get_hours(username, min(dates), max(dates))
            for tb in result.get('userReport', []):
                date = tb['startDate'][:10]
                key = f"{username}|{date}"
                existing[key] = existing.get(key, 0.0) + float(tb.get('hours', 0))
        except Exception as e:
            # Remove pre-initialized keys so they show as "? unknown" on failure
            for d in dates:
                existing.pop(f"{username}|{d}", None)
            api_errors[username] = str(e)

    # Compute expected start/end times for display in the review table.
    # Start each day at 08:00 + existing hours already logged, then stack entries.
    review_stacks = defaultdict(list)
    for e in entries:
        if not e.get('q360id'):
            continue
        for d in e.get('days', []):
            if d.get('date') and float(d.get('hours', 0)) > 0:
                review_stacks[(e['username'], d['date'])].append(
                    (int(e.get('row_num', 0)), d)
                )
    for (username, date), stack in review_stacks.items():
        stack.sort(key=lambda x: x[0])
        existing_h = existing.get(f"{username}|{date}", 0.0)
        current = datetime.strptime(date + ' 08:00', '%Y-%m-%d %H:%M') + timedelta(hours=existing_h)
        for _, d in stack:
            d['start_time'] = current.strftime('%H:%M')
            end_dt = current + timedelta(hours=float(d['hours']))
            d['end_time'] = end_dt.strftime('%H:%M')
            current = end_dt

    return render_template('bulk/_review.html',
                           entries=entries,
                           existing=existing,
                           api_errors=api_errors,
                           entries_json=entries_json)


@bp.route('/submit', methods=['POST'])
@login_required
def submit():
    entries_json = request.form.get('entries', '[]')
    try:
        entries = json.loads(entries_json)
    except Exception:
        return '<div class="alert alert-danger">Invalid submission data.</div>'

    import traceback as _tb
    try:
        return _do_submit(entries)
    except Exception:
        return (f'<div class="alert alert-danger"><strong>Unexpected error — please report:'
                f'</strong><pre style="font-size:.75rem;white-space:pre-wrap">'
                f'{_tb.format_exc()}</pre></div>')


def _do_submit(entries):
    from collections import defaultdict
    svc = _svc()
    results = []

    # Fetch existing hours for all users/dates
    user_dates = defaultdict(set)
    for e in entries:
        if e.get('needs_attention') or not e.get('q360id'):
            continue
        for d in e.get('days', []):
            if float(d.get('hours', 0)) > 0 and d.get('date'):
                user_dates[e['username']].add(d['date'])

    existing = {}
    for username, dates in user_dates.items():
        if not dates:
            continue
        try:
            result = svc.get_hours(username, min(dates), max(dates))
            for tb in result.get('userReport', []):
                key = f"{username}|{tb['startDate'][:10]}"
                existing[key] = existing.get(key, 0.0) + float(tb.get('hours', 0))
        except Exception:
            pass

    # Recalculate time slots server-side based on row_num ordering
    day_stacks = defaultdict(list)  # (username, date) -> [(row_num, entry, day_dict)]
    for e in entries:
        if e.get('needs_attention') or not e.get('q360id'):
            continue
        for d in e.get('days', []):
            if not d.get('date'):
                continue
            hours = float(d.get('hours', 0))
            key = f"{e['username']}|{d['date']}"
            existing_h = existing.get(key, 0.0)
            if hours > 0 and existing_h + hours <= 8.0:
                day_stacks[(e['username'], d['date'])].append((int(e['row_num']), e, d))

    for (username, date), stack in day_stacks.items():
        stack.sort(key=lambda x: x[0])
        existing_h = existing.get(f"{username}|{date}", 0.0)
        current = datetime.strptime(date + ' 08:00', '%Y-%m-%d %H:%M') + timedelta(hours=existing_h)
        for _, _, d in stack:
            d['start_time'] = current.strftime('%H:%M')
            end = current + timedelta(hours=float(d['hours']))
            d['end_time'] = end.strftime('%H:%M')
            current = end

    for e in entries:
        if e.get('needs_attention') or not e.get('q360id'):
            continue
        for d in e.get('days', []):
            if not d.get('date'):
                continue
            hours = float(d.get('hours', 0))
            if hours <= 0:
                continue
            key = f"{e['username']}|{d['date']}"
            existing_h = existing.get(key, 0.0)
            if existing_h + hours > 8.0:
                results.append({'employee': e.get('username', ''), 'day': d.get('day', ''),
                                'hours': hours, 'success': None,
                                'error': f'Skipped — {existing_h}h already logged, adding {hours}h would exceed 8h'})
                continue
            try:
                date = d['date']
                start_time = d.get('start_time', '08:00')
                end_time = d.get('end_time', '16:00')
                sd = datetime.strptime(f"{date} {start_time}", '%Y-%m-%d %H:%M')
                ed = datetime.strptime(f"{date} {end_time}", '%Y-%m-%d %H:%M')
                if ed <= sd:
                    ed = sd + timedelta(hours=hours)
                s = f"{date}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
                e_str = f"{date}%20{end_time[:2]}%3A{end_time[3:5]}%3A00.000"
                delta = ed - sd
                logtime = f"{str(delta)[:-6]}.{str(delta)[-5:-3]}"
                note = e.get('comment') or 'POWERED BY Q360 AUTO APP'
                svc.submit_hours(
                    e['q360id'], s, e_str, logtime, note,
                    e.get('company', 'CONNEX TELECOMMUNICATIONS INC.'),
                    e['username'], e['category']
                )
                results.append({'employee': e.get('username', ''), 'day': d['day'],
                                'hours': hours, 'success': True, 'error': None})
            except Exception as ex:
                results.append({'employee': e.get('username', ''), 'day': d.get('day', ''),
                                'hours': hours, 'success': False, 'error': str(ex)})

    return render_template('bulk/_result.html', results=results)


@bp.route('/save-username', methods=['POST'])
@login_required
def save_username():
    employee_name = request.form.get('employee_name', '').strip()
    q360_username = request.form.get('q360_username', '').strip()
    if not employee_name or not q360_username:
        return ('Missing fields', 400)
    db = get_db()
    db.execute(
        'INSERT INTO username_map (employee_name, q360_username) VALUES (?, ?)'
        ' ON CONFLICT(employee_name) DO UPDATE SET q360_username=excluded.q360_username',
        (employee_name, q360_username)
    )
    db.commit()
    return ('', 204)
