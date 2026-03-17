import json
from datetime import datetime, timedelta

import pandas as pd
from flask import Blueprint, render_template, request, session

from app.routes.auth import login_required
from app.services.q360 import Q360Service, CATEGORIES, COMPANIES

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

        q360id = row.get('Q360ID')
        has_q360 = q360id is not None and str(q360id) != 'nan' and str(q360id) != ''
        q360id_str = str(int(float(q360id))) if has_q360 else ''

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
            'q360id': q360id_str,
            'needs_attention': not has_q360,
            'suggested': False,
            'category': DEFAULT_CATEGORY if has_q360 else '',
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
    file = request.files.get('file')
    if not file:
        return '<div class="alert alert-danger">Please provide a file.</div>'
    try:
        grouped = _parse_excel(file)
    except Exception as e:
        return f'<div class="alert alert-danger">Failed to parse file: {e}</div>'
    # Determine which day columns have any data
    active_days = [d for d in DAY_COLS if any(
        r['days'][d]['hours'] > 0 for u in grouped for r in u['rows']
    )]

    # Fetch live Q360 projects for each user to map Excel projectno → resq_zoom_key (task number)
    svc = _svc()
    live_by_user = {}
    for u in grouped:
        try:
            live_by_user[u['username']] = svc.get_projects(u['username'])
        except Exception:
            live_by_user[u['username']] = {}

    # Remap each row's q360id (Excel short projectno) to resq_zoom_key (actual task number)
    for u in grouped:
        live = live_by_user.get(u['username'], {})
        projectno_map = {}  # Excel short ID → resq_zoom_key
        for rzk, item in live.items():
            pno = str(item.get('projectno', '')).strip()
            if pno:
                projectno_map[pno] = rzk

        for r in u['rows']:
            qid = r.get('q360id', '')
            if not qid:
                continue
            if qid in live:
                # Already a valid resq_zoom_key — update description
                desc = live[qid].get('description', '').strip()
                if desc:
                    r['customer'] = desc
            elif qid in projectno_map:
                rzk = projectno_map[qid]
                r['q360id'] = rzk
                item = live[rzk]
                desc = item.get('description', '').strip()
                if desc:
                    r['customer'] = desc
                r['category'] = item.get('category', '') or DEFAULT_CATEGORY
                r['needs_attention'] = False
            # Remap any recommended_q360ids too
            if r.get('recommended_q360ids'):
                r['recommended_q360ids'] = [
                    projectno_map.get(rid, rid) for rid in r['recommended_q360ids']
                ]

    # Build user_projects from live Q360 data (keyed by resq_zoom_key) for dropdowns
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

    all_weeks = sorted(set(r['week_num'] for u in grouped for r in u['rows']))
    return render_template('bulk/_table.html', grouped=grouped, categories=CATEGORIES,
                           default_category=DEFAULT_CATEGORY, active_days=active_days,
                           user_projects=user_projects,
                           all_weeks=all_weeks)


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

    svc = _svc()
    results = []
    from collections import defaultdict

    # Fetch existing hours for all users/dates
    user_dates = defaultdict(set)
    for e in entries:
        if e.get('needs_attention') or not e.get('q360id'):
            continue
        for d in e.get('days', []):
            if float(d.get('hours', 0)) > 0:
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
            hours = float(d.get('hours', 0))
            key = f"{e['username']}|{d['date']}"
            existing_h = existing.get(key, 0.0)
            if hours > 0 and existing_h + hours <= 8.0:
                day_stacks[(e['username'], d['date'])].append((int(e['row_num']), e, d))

    for stack in day_stacks.values():
        stack.sort(key=lambda x: x[0])
        current = datetime.strptime(stack[0][2]['date'] + ' 08:00', '%Y-%m-%d %H:%M')
        for _, _, d in stack:
            d['start_time'] = current.strftime('%H:%M')
            end = current + timedelta(hours=float(d['hours']))
            d['end_time'] = end.strftime('%H:%M')
            current = end

    for e in entries:
        if e.get('needs_attention') or not e.get('q360id'):
            continue
        for d in e.get('days', []):
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
