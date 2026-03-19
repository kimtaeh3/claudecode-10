from collections import defaultdict
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, request, session
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


def ontario_holidays(year: int) -> set:
    """Return set of Ontario statutory holiday dates for the given year."""
    easter = _easter_sunday(year)
    holidays = {
        _observed(date(year, 1, 1)),           # New Year's Day
        _nth_weekday(year, 2, 0, 3),           # Family Day (3rd Mon Feb)
        easter - timedelta(days=2),            # Good Friday
        _nth_weekday(year, 5, 0, 1)            # Victoria Day: last Mon on/before May 25
        if _nth_weekday(year, 5, 0, 1) <= date(year, 5, 25)
        else _nth_weekday(year, 5, 0, 1) - timedelta(weeks=1),
        _observed(date(year, 7, 1)),           # Canada Day
        _nth_weekday(year, 9, 0, 1),           # Labour Day (1st Mon Sep)
        _nth_weekday(year, 10, 0, 2),          # Thanksgiving (2nd Mon Oct)
        _observed(date(year, 12, 25)),         # Christmas Day
        _observed(date(year, 12, 26)),         # Boxing Day
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
    vic = _nth_weekday(year, 5, 0, 1)
    if vic > date(year, 5, 25):
        vic -= timedelta(weeks=1)
    hols = [
        (_observed(date(year, 1, 1)),       "New Year's Day"),
        (_nth_weekday(year, 2, 0, 3),        "Family Day"),
        (easter - timedelta(days=2),         "Good Friday"),
        (vic,                                "Victoria Day"),
        (_observed(date(year, 7, 1)),        "Canada Day"),
        (_nth_weekday(year, 9, 0, 1),        "Labour Day"),
        (_nth_weekday(year, 10, 0, 2),       "Thanksgiving"),
        (_observed(date(year, 12, 25)),      "Christmas Day"),
        (_observed(date(year, 12, 26)),      "Boxing Day"),
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

    # Name lookup: username → full name from team_member
    name_rows = db.execute('SELECT username, name FROM team_member').fetchall()
    member_names = {r['username']: r['name'] for r in name_rows if r['name']}

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
    if team_filter and team_filter != 'All':
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

    # Sorted week list with per-week available hours
    all_week_keys = sorted({r['week'] for r in rows})
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
        weeks.append({'key': wk, 'label': label, 'date': date_label, 'avail': avail, 'avail_raw': avail_raw})

    # Collect all categories seen across all users/weeks
    all_cats = sorted({cat for u in user_weeks.values() for wk in u.values() for cat in wk['cats']})

    # Per-user summary
    users = []
    for username in sorted(user_weeks.keys()):
        wdata = user_weeks[username]
        total_all = sum(w['total'] for w in wdata.values())
        total_bill = sum(w['billable'] for w in wdata.values())
        total_nonbill = sum(w['nonbillable'] for w in wdata.values())
        weeks_worked = len(wdata)
        # Available hours = filter-range available work hours (matches Avail Hrs row)
        user_avail = total_avail
        util_pct = (total_bill / user_avail * 100) if user_avail > 0 else 0
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
            'week_data': wdata,
            'total': total_all,
            'billable': total_bill,
            'nonbillable': total_nonbill,
            'util_pct': util_pct,
            'avg_per_week': avg_per_week,
            'weeks_worked': weeks_worked,
            'avail_hours': user_avail,
            'cat_totals': dict(cat_totals),
            'cat_proj_totals': {c: dict(p) for c, p in cat_proj_totals.items()},
        })

    total_avail_raw = _available_hours(start, end, set())
    return render_template('forecast/index.html',
                           users=users, weeks=weeks,
                           teams=teams, team_filter=team_filter,
                           start=start, end=end,
                           total_avail=total_avail,
                           total_avail_raw=total_avail_raw,
                           all_cats=all_cats,
                           nb_projects=nb_projects,
                           holidays=sorted(h.isoformat() for h in holidays))
