from collections import defaultdict
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, request, session, jsonify
from app.routes.auth import login_required
from app.db import get_db

bp = Blueprint('forecast', __name__, url_prefix='/forecast')

NON_BILLABLE = {'TRAVEL', 'ON-CALL', 'ADMIN', 'HOLIDAY', 'PTO', 'VACATION'}


# ── Ontario Canada statutory holidays ────────────────────────────────────────

def _easter_sunday(year: int) -> date:
    """Butcher's algorithm for Easter Sunday."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence (1-based) of weekday (0=Mon) in given month."""
    d = date(year, month, 1)
    days_ahead = weekday - d.weekday()
    if days_ahead < 0:
        days_ahead += 7
    first = d + timedelta(days=days_ahead)
    return first + timedelta(weeks=n - 1)


def _observed(d: date) -> date:
    """If holiday falls on Saturday → Friday; Sunday → Monday."""
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _christmas_boxing(year: int) -> tuple:
    """Return observed (christmas, boxing_day) dates, handling collision.
    When Boxing Day's normal observed date would land on Christmas Day's
    observed date (e.g. 2026: Fri/Sat), Boxing Day shifts to Monday."""
    christmas = _observed(date(year, 12, 25))
    boxing_raw = date(year, 12, 26)
    boxing = _observed(boxing_raw)
    if boxing == christmas:
        # Find next Monday
        boxing = christmas + timedelta(days=(7 - christmas.weekday()) % 7 or 7)
    return christmas, boxing


def _victoria_day(year: int) -> date:
    """Last Monday on or before May 24."""
    may24 = date(year, 5, 24)
    return may24 - timedelta(days=may24.weekday())


def ontario_holidays(year: int) -> set:
    """Return set of Ontario statutory holiday dates for the given year."""
    easter = _easter_sunday(year)
    christmas, boxing = _christmas_boxing(year)
    holidays = {
        _observed(date(year, 1, 1)),           # New Year's Day
        _nth_weekday(year, 2, 0, 3),           # Family Day (3rd Mon Feb)
        easter - timedelta(days=2),            # Good Friday
        _victoria_day(year),                   # Victoria Day (last Mon on/before May 24)
        _observed(date(year, 7, 1)),           # Canada Day
        _nth_weekday(year, 8, 0, 1),           # Civic Holiday (1st Mon Aug) — Ontario
        _nth_weekday(year, 9, 0, 1),           # Labour Day (1st Mon Sep)
        _nth_weekday(year, 10, 0, 2),          # Thanksgiving (2nd Mon Oct)
        christmas,
        boxing,
    }
    return holidays


def _holiday_set(start_str: str, end_str: str) -> set:
    """All Ontario holiday dates (as date objects) between start and end."""
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    years = range(start.year, end.year + 1)
    all_hols = set()
    for y in years:
        all_hols |= ontario_holidays(y)
    return {h for h in all_hols if start <= h <= end}


def _available_hours(start_str: str, end_str: str, holidays: set) -> float:
    """Workdays (Mon–Fri, excl. holidays) × 8h between start and end inclusive."""
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    hours = 0.0
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:  # Mon–Fri, not a holiday
            hours += 8.0
        d += timedelta(days=1)
    return hours


def ontario_holidays_named(year: int) -> list:
    """Return sorted list of (date, name) for Ontario statutory holidays."""
    easter = _easter_sunday(year)
    christmas, boxing = _christmas_boxing(year)
    hols = [
        (_observed(date(year, 1, 1)),        "New Year's Day"),
        (_nth_weekday(year, 2, 0, 3),        "Family Day"),
        (easter - timedelta(days=2),         "Good Friday"),
        (_victoria_day(year),                "Victoria Day"),
        (_observed(date(year, 7, 1)),        "Canada Day"),
        (_nth_weekday(year, 8, 0, 1),        "Civic Holiday"),
        (_nth_weekday(year, 9, 0, 1),        "Labour Day"),
        (_nth_weekday(year, 10, 0, 2),       "Thanksgiving"),
        (christmas,                          "Christmas Day"),
        (boxing,                             "Boxing Day"),
    ]
    return sorted(hols, key=lambda x: x[0])


def _week_bounds(week_key: str):
    """Return (monday, sunday) for the week, clipped to the key's year boundary.

    strftime('%Y-W%W') splits year-boundary weeks across two keys (e.g. 2025-W52
    covers Dec 29–31 and 2026-W00 covers Jan 1–4 for the same Mon–Sun span).
    Clipping to the key's year ensures each key only counts its own days.
    """
    yr_str, wn = week_key.split('-W')
    yr = int(yr_str)
    monday = datetime.strptime(f'{yr}-{int(wn)}-1', '%Y-%W-%w').date()
    sunday = monday + timedelta(days=6)
    # Clip to the key's calendar year
    if monday.year < yr:
        monday = date(yr, 1, 1)
    if sunday.year > yr:
        sunday = date(yr, 12, 31)
    return monday, sunday


def _week_available_hours(week_key: str, range_start: str, range_end: str,
                           holidays: set) -> float:
    """Available hours for a single week key, clipped to [range_start, range_end]."""
    monday, sunday = _week_bounds(week_key)
    ws = max(monday, date.fromisoformat(range_start))
    we = min(sunday, date.fromisoformat(range_end))
    if ws > we:
        return 0.0
    return _available_hours(ws.isoformat(), we.isoformat(), holidays)


def _week_monday(week_key: str) -> datetime:
    monday, _ = _week_bounds(week_key)
    return datetime(monday.year, monday.month, monday.day)


# ── Route ─────────────────────────────────────────────────────────────────────

@bp.route('/')
@login_required
def index():
    db = get_db()

    today = date.today()
    default_start = today.replace(day=1).isoformat()
    default_end = today.isoformat()
    start = request.args.get('start', default_start)
    end = request.args.get('end', default_end)
    team_filter = request.args.get('team', '')
    users_filter_raw = request.args.get('users', '')
    users_filter_set = {u.strip() for u in users_filter_raw.split(',') if u.strip()} if users_filter_raw else set()
    project_filter = request.args.get('project', '')
    view_mode = request.args.get('view', 'month')

    # Name lookup: username → full name + member_type + employment dates from team_member
    name_rows = db.execute('SELECT username, name, member_type, start_date, end_date FROM team_member').fetchall()
    member_names = {r['username']: r['name'] for r in name_rows if r['name']}
    member_types_map = {r['username']: (r['member_type'] or 'Employee (100%)') for r in name_rows}
    member_start_map = {r['username']: r['start_date'] for r in name_rows if r['start_date']}
    member_end_map   = {r['username']: r['end_date']   for r in name_rows if r['end_date']}

    # Contractor project allocations (by username)
    try:
        alloc_rows = db.execute(
            'SELECT tm.username, ca.project_name, ca.utilization_pct, ca.start_date, ca.end_date '
            'FROM contractor_allocation ca '
            'JOIN team_member tm ON tm.id = ca.member_id ORDER BY ca.id'
        ).fetchall()
    except Exception:
        alloc_rows = []
    contractor_allocs_map = defaultdict(list)
    for r in alloc_rows:
        contractor_allocs_map[r['username']].append({
            'project_name': r['project_name'],
            'utilization_pct': r['utilization_pct'],
            'start_date': r['start_date'] or '',
            'end_date': r['end_date'] or '',
        })

    # Available teams
    rows = db.execute('SELECT team FROM team_member').fetchall()
    seen = set()
    for r in rows:
        for t in r['team'].split(','):
            t = t.strip()
            if t:
                seen.add(t)
    teams = ['All'] + sorted(t for t in seen if t != 'All')

    # Non-billable project names (partial, case-insensitive)
    nb_rows = db.execute('SELECT name FROM nonbillable_project').fetchall()
    nb_projects = [r['name'].lower() for r in nb_rows]

    def _is_nonbillable_project(project: str) -> bool:
        pl = project.lower()
        return any(nb in pl for nb in nb_projects)

    # Fetch individual hour entries to apply project-name non-billable check in Python
    q = '''
        SELECT bh.username, bh.employee, bh.date, bh.hours, bh.category, bh.project,
               strftime('%Y-W%W', bh.date) AS week
        FROM bulk_hours bh
        WHERE bh.date >= ? AND bh.date <= ?
    '''
    params = [start, end]
    if team_filter and team_filter not in ('All', 'selected'):
        q += (" AND bh.username IN (SELECT username FROM team_member "
              "WHERE INSTR(',' || team || ',', ',' || ? || ',') > 0)")
        params.append(team_filter)
    q += ' ORDER BY bh.username, bh.date'

    rows = db.execute(q, params).fetchall()

    # Holiday set for the range (computed once)
    holidays = _holiday_set(start, end)
    total_avail = _available_hours(start, end, holidays)

    # TRAVEL, HOLIDAY, PTO, VACATION → display as "Holiday" (non-billable)
    # ON-CALL → display as "On-Call" (billable, counts toward util%)
    # ADMIN → non-billable
    HOLIDAY_CATS = {'TRAVEL', 'HOLIDAY'}
    NON_BILLABLE_CATS = HOLIDAY_CATS | {'ADMIN', 'VACATION', 'PTO'}

    def _display_cat(raw_cat: str) -> str:
        if raw_cat in ('VACATION', 'PTO'):
            return 'Vacation'
        if raw_cat in HOLIDAY_CATS:  # TRAVEL, HOLIDAY
            return 'Holiday'
        if raw_cat == 'ON-CALL':
            return 'On-Call'
        return raw_cat

    # Build per-user data, applying both category and project-name non-billable rules
    # user_weeks[u][wk] = {total, billable, nonbillable, cats: {disp_cat: hours},
    #                       cat_projects: {disp_cat: {project: hours}}}
    user_weeks = defaultdict(lambda: defaultdict(lambda: {
        'total': 0.0, 'billable': 0.0, 'nonbillable': 0.0,
        'cats': defaultdict(float),
        'cat_projects': defaultdict(lambda: defaultdict(float)),
    }))
    user_employee = {}
    user_min_date = {}
    user_max_date = {}
    for r in rows:
        u = r['username']
        wk = r['week']
        hrs = float(r['hours'] or 0)
        raw_cat = r['category'] or 'OTHER'
        nb_by_project = _is_nonbillable_project(r['project'] or '')
        is_nb = (raw_cat in NON_BILLABLE_CATS) or nb_by_project
        # Category drives the row label; project overrides mark the same category as non-billable
        # e.g. VOICE-CCAPPDEV on INTERNAL CONNEX → shows as "VOICE-CCAPPDEV (Internal)" in yellow
        base_cat = _display_cat(raw_cat)
        if nb_by_project and raw_cat not in NON_BILLABLE_CATS:
            disp_cat = base_cat + ' (Internal)'
        else:
            disp_cat = base_cat
        proj_name = (r['project'] or '').strip() or '(no project)'
        user_weeks[u][wk]['total'] += hrs
        user_weeks[u][wk]['cats'][disp_cat] += hrs
        user_weeks[u][wk]['cat_projects'][disp_cat][proj_name] += hrs
        if is_nb:
            user_weeks[u][wk]['nonbillable'] += hrs
        else:
            user_weeks[u][wk]['billable'] += hrs
        user_employee[u] = member_names.get(u) or r['employee'] or u
        if u not in user_min_date or r['date'] < user_min_date[u]:
            user_min_date[u] = r['date']
        if u not in user_max_date or r['date'] > user_max_date[u]:
            user_max_date[u] = r['date']

    # Include team members with no bulk_hours so they still appear with zeros
    if team_filter and team_filter not in ('All', 'selected'):
        zero_members = db.execute(
            "SELECT username FROM team_member "
            "WHERE INSTR(',' || team || ',', ',' || ? || ',') > 0",
            (team_filter,)).fetchall()
    else:
        zero_members = db.execute('SELECT username FROM team_member').fetchall()
    for zm in zero_members:
        u = zm['username']
        if u not in user_weeks:
            user_weeks[u]  # touch to create empty defaultdict entry
            user_employee[u] = member_names.get(u) or u

    # Apply users_filter_set early so zero-entry users are also filtered
    if users_filter_set:
        for u in list(user_weeks.keys()):
            if u not in users_filter_set:
                del user_weeks[u]

    # Inject synthetic billable hours for contractors (no Q360 data)
    def _weeks_in_range(s: str, e: str) -> set:
        """Return all %Y-W%W keys in range, iterating day-by-day to catch year-boundary splits."""
        sd, ed = date.fromisoformat(s), date.fromisoformat(e)
        keys, d = set(), sd
        while d <= ed:
            keys.add(d.strftime('%Y-W%W'))
            d += timedelta(days=1)
        return keys

    contractor_week_keys = set()
    for username, allocs in contractor_allocs_map.items():
        if username not in user_weeks:
            continue
        mtype = member_types_map.get(username, 'Employee (100%)')
        if not mtype.startswith('Contractor'):
            continue
        for alloc in allocs:
            pct = alloc['utilization_pct'] / 100.0
            project_name = alloc['project_name'] or '(no project)'
            # Effective range = intersection of filter, allocation, and member employment
            eff_start = start
            eff_end = end
            if alloc['start_date']:
                eff_start = max(eff_start, alloc['start_date'])
            if alloc['end_date']:
                eff_end = min(eff_end, alloc['end_date'])
            if username in member_start_map:
                eff_start = max(eff_start, member_start_map[username])
            if username in member_end_map:
                eff_end = min(eff_end, member_end_map[username])
            if eff_start > eff_end:
                continue
            for wk in _weeks_in_range(eff_start, eff_end):
                wk_hrs = _week_available_hours(wk, eff_start, eff_end, holidays) * pct
                if wk_hrs <= 0:
                    continue
                contractor_week_keys.add(wk)
                wd = user_weeks[username][wk]
                wd['total'] += wk_hrs
                wd['billable'] += wk_hrs
                wd['cats']['Billable'] += wk_hrs
                wd['cat_projects']['Billable'][project_name] += wk_hrs

    # Sorted week list with per-week available hours
    all_week_keys = sorted({r['week'] for r in rows} | contractor_week_keys)
    weeks = []
    for wk in all_week_keys:
        try:
            mon = _week_monday(wk)
            label = f"Wk {int(wk.split('-W')[1])}"
            date_label = mon.strftime('%b %-d')
        except Exception:
            label = wk
            date_label = ''
        avail = _week_available_hours(wk, start, end, holidays)
        avail_raw = _week_available_hours(wk, start, end, set())
        try:
            month_key = mon.strftime('%Y-%m')
        except Exception:
            month_key = ''
        weeks.append({'key': wk, 'label': label, 'date': date_label, 'avail': avail, 'avail_raw': avail_raw, 'month_key': month_key})

    # Sum of per-week values — matches exactly what's shown in the Avail Hrs row
    weeks_avail = sum(w['avail'] for w in weeks)       # blue numbers (excl. holidays)
    weeks_avail_raw = sum(w['avail_raw'] for w in weeks)  # bracket numbers (incl. holidays)

    # Collect all categories seen across all users/weeks
    all_cats = sorted({cat for u in user_weeks.values() for wk in u.values() for cat in wk['cats']})

    def _user_avail(username):
        """Available hours for this user based on member_type, contractor allocations, and employment dates."""
        mtype = member_types_map.get(username, 'Employee (100%)')
        base = 0.5 if '50%' in mtype else 1.0
        if mtype.startswith('Contractor'):
            allocs = contractor_allocs_map.get(username, [])
            if allocs:
                total_pct = sum(a['utilization_pct'] for a in allocs) / 100.0
                base *= min(total_pct, 1.0)
        # Clamp to employment period if set
        eff_start = max(start, member_start_map[username]) if username in member_start_map else start
        eff_end   = min(end,   member_end_map[username])   if username in member_end_map   else end
        if eff_start > eff_end:
            return 0.0, 0.0
        if eff_start == start and eff_end == end:
            return weeks_avail * base, weeks_avail_raw * base
        u_avail     = sum(_week_available_hours(w['key'], eff_start, eff_end, holidays) for w in weeks) * base
        u_avail_raw = sum(_week_available_hours(w['key'], eff_start, eff_end, set())    for w in weeks) * base
        return u_avail, u_avail_raw

    # Per-user summary
    users = []
    for username in sorted(user_weeks.keys()):
        # Skip employees whose employment period doesn't overlap with the filter range
        emp_end   = member_end_map.get(username)
        emp_start = member_start_map.get(username)
        if emp_end and emp_end < start:
            continue  # left before filter window
        if emp_start and emp_start > end:
            continue  # joined after filter window
        wdata = user_weeks[username]
        total_all = sum(w['total'] for w in wdata.values())
        total_bill = sum(w['billable'] for w in wdata.values())
        total_nonbill = sum(w['nonbillable'] for w in wdata.values())
        weeks_worked = len(wdata)
        u_avail, u_avail_raw = _user_avail(username)
        # Util%   = billable / blue total (excl. holidays)
        # Logged% = total    / bracket total (incl. holidays)
        util_pct = (total_bill / u_avail * 100) if u_avail > 0 else 0
        logged_pct = (total_all / u_avail_raw * 100) if u_avail_raw > 0 else 0
        avg_per_week = (total_all / weeks_worked) if weeks_worked > 0 else 0
        # Per-category and per-category-project totals across all weeks
        cat_totals = defaultdict(float)
        cat_proj_totals = defaultdict(lambda: defaultdict(float))
        for wk_data in wdata.values():
            for cat, hrs in wk_data['cats'].items():
                cat_totals[cat] += hrs
            for cat, projs in wk_data['cat_projects'].items():
                for proj, hrs in projs.items():
                    cat_proj_totals[cat][proj] += hrs

        users.append({
            'username': username,
            'employee': user_employee.get(username, username),
            'member_type': member_types_map.get(username, 'Employee (100%)'),
            'contractor_allocs': contractor_allocs_map.get(username, []),
            'start_date': member_start_map.get(username, ''),
            'end_date': member_end_map.get(username, ''),
            'week_data': wdata,
            'total': total_all,
            'billable': total_bill,
            'nonbillable': total_nonbill,
            'util_pct': util_pct,
            'logged_pct': logged_pct,
            'avg_per_week': avg_per_week,
            'weeks_worked': weeks_worked,
            'avail_hours': u_avail,
            'cat_totals': dict(cat_totals),
            'cat_proj_totals': {c: dict(p) for c, p in cat_proj_totals.items()},
        })

    total_avail_raw = _available_hours(start, end, set())
    saved_filters = db.execute(
        'SELECT id, name, team, start, end, usernames, project FROM saved_filter WHERE username = ? ORDER BY name',
        (session['user_id'],)
    ).fetchall()
    return render_template('forecast/index.html',
                           users=users, weeks=weeks,
                           teams=teams, team_filter=team_filter,
                           start=start, end=end,
                           users_filter=users_filter_raw,
                           project_filter=project_filter,
                           total_avail=total_avail,
                           total_avail_raw=total_avail_raw,
                           all_cats=all_cats,
                           nb_projects=nb_projects,
                           holidays=sorted(h.isoformat() for h in holidays),
                           saved_filters=saved_filters,
                           view_mode=view_mode)


@bp.route('/filters/save', methods=['POST'])
@login_required
def save_filter():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    team = (data.get('team') or 'All').strip()
    start = (data.get('start') or '').strip()
    end = (data.get('end') or '').strip()
    usernames = (data.get('usernames') or '').strip()
    project = (data.get('project') or '').strip()
    if not name or not start or not end:
        return jsonify({'error': 'Name, start, and end are required'}), 400
    db = get_db()
    db.execute(
        'INSERT INTO saved_filter (username, name, team, start, end, usernames, project) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (session['user_id'], name, team, start, end, usernames, project)
    )
    db.commit()
    filters = db.execute(
        'SELECT id, name, team, start, end, usernames, project FROM saved_filter WHERE username = ? ORDER BY name',
        (session['user_id'],)
    ).fetchall()
    return jsonify({'filters': [dict(f) for f in filters]})


@bp.route('/filters/rename/<int:filter_id>', methods=['POST'])
@login_required
def rename_filter(filter_id):
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    db = get_db()
    db.execute('UPDATE saved_filter SET name = ? WHERE id = ? AND username = ?',
               (name, filter_id, session['user_id']))
    db.commit()
    return jsonify({'ok': True})


@bp.route('/filters/delete/<int:filter_id>', methods=['DELETE'])
@login_required
def delete_filter(filter_id):
    db = get_db()
    db.execute('DELETE FROM saved_filter WHERE id = ? AND username = ?',
               (filter_id, session['user_id']))
    db.commit()
    filters = db.execute(
        'SELECT id, name, team, start, end, usernames, project FROM saved_filter WHERE username = ? ORDER BY name',
        (session['user_id'],)
    ).fetchall()
    return jsonify({'filters': [dict(f) for f in filters]})
