"""
Q360Service — wraps all API calls to websupport.connexservice.ca.
Credentials are passed explicitly; no Flask session dependency.
"""

import json
import urllib3
from datetime import datetime, timedelta
from itertools import groupby
from urllib.parse import urlencode, quote_plus, unquote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests


BASE_URL = 'https://websupport.connexservice.ca'
AJAX_URL = f'{BASE_URL}/ajax/'
LOGIN_URL = f'{AJAX_URL}?_a=authenticate&_r=action=login'
CONTROLLER_LOGIN = f'{BASE_URL}/controller.php?action=login'

COMPANY_MAP = {
    'CONNEX QUEBEC INC.': '02',
    'PULSE SERVICES INC.': '03',
    'CONNEX USA': '04',
}

CATEGORIES = [
    'CABLE - INSTALL 1', 'CABLE - INSTALL 2', 'CABLE - INSTALL 3', 'CABLE - PM',
    'DATA - NTWKARCH', 'DATA - NTWKTECH', 'DATA - PM', 'HELPDESK',
    'VOICE - PM', 'VOICE - UCCONSULT', 'VOICE - UCCINSTALL', 'VOICE - UCCSUPPORT',
    'VOICE - UCCSYSDS', 'VOICE- CCAPPDEV', 'VOICE- CCARCH', 'VOICE- CCBA',
    'VOICE- CCBC', 'VOICE- CCINT', 'VOICE- CCPM', 'VOICE- CCTEST',
    'TRAVEL', 'ON-CALL', 'ADMIN', 'HOLIDAY', 'PTO', 'VACATION',
]

COMPANIES = [
    'CONNEX TELECOMMUNICATIONS INC.',
    'CONNEX QUEBEC INC.',
    'PULSE SERVICES INC.',
    'CONNEX USA',
]


class Q360Service:
    def __init__(self, user_id: str, password: str):
        self.user_id = user_id
        self.password = password
        self._session = None

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    def _auth_header(self) -> dict:
        return {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': CONTROLLER_LOGIN,
        }

    def _get_session(self) -> requests.Session:
        """Return an authenticated requests.Session (lazy init)."""
        s = requests.Session()
        cookies = {'cookies_are': 'working'}
        s.get(CONTROLLER_LOGIN, cookies=cookies, verify=False)
        s.post(
            LOGIN_URL,
            headers=self._auth_header(),
            data={'jsonRequest': f'{{"userid":"{self.user_id}","password":"{self.password}","touch":"false"}}'},
            cookies=cookies,
            verify=False,
        )
        return s

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = self._get_session()
        return self._session

    def login(self) -> dict:
        """Authenticate and return the raw JSON response dict."""
        s = requests.Session()
        cookies = {'cookies_are': 'working'}
        s.get(CONTROLLER_LOGIN, cookies=cookies, verify=False)
        r = s.post(
            LOGIN_URL,
            headers=self._auth_header(),
            data={'jsonRequest': f'{{"userid":"{self.user_id}","password":"{self.password}","touch":"false"}}'},
            cookies=cookies,
            verify=False,
        )
        return json.loads(r.text)

    # ------------------------------------------------------------------ #
    # Fetch hours
    # ------------------------------------------------------------------ #

    def get_hours(self, target_user_id: str, start_date: str, end_date: str) -> dict:
        """
        Fetch timebill data for target_user_id between start_date and end_date.
        Returns a dict with keys: timePeriod, totalHours, userReport,
        date, weeklyUserReport, weeklyTotalReport, projectTotalReport.
        """
        r = self.session.post(
            AJAX_URL,
            headers=self._auth_header(),
            data={
                'userid': target_user_id,
                'startdate': start_date,
                'enddate': end_date,
                '_a': 'get_timebill_byuseriddetail',
            },
            cookies={'cookies_are': 'working'},
            verify=False,
        )
        raw = r.text
        user_report = self._parse_timebills(raw)
        total_hours = user_report.pop()
        return {
            'timePeriod': {'start': start_date, 'end': end_date},
            'totalHours': total_hours,
            'userReport': user_report,
            'date': self._parse_dates(raw),
            'weeklyUserReport': self._parse_weekly(raw),
            'weeklyTotalReport': self._parse_weekly_total(raw),
            'projectTotalReport': self._parse_project_total(raw),
        }

    # ------------------------------------------------------------------ #
    # Projects
    # ------------------------------------------------------------------ #

    def get_projects(self, target_user_id: str = None) -> dict:
        uid = target_user_id or self.user_id
        today = datetime.today().strftime('%Y-%m-%d')
        payload = (
            f'EndDate={today}&InclActivity=Y&InclAltRep=Y&InclCalls=Y&InclCallsCSR=Y'
            f'&InclOppTasks=Y&InclOppor=Y&InclQuotes=Y&InclTasksAssign=Y&InclTasksResp=Y'
            f'&_a=mytasklist_get&_pversion=d101&mobileflag=N&numdays=0&userid={uid}'
        )
        headers = {
            'Connection': 'keep-alive',
            'Accept': 'text/plain, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0',
            'Origin': BASE_URL,
            'Referer': f'{BASE_URL}/controller.php?action=mytasklist',
        }
        r = self.session.post(AJAX_URL, headers=headers, data=payload,
                              cookies={'cookies_are': 'working'}, verify=False, timeout=25)
        data = json.loads(r.text)['data']
        return {item['resq_zoom_key']: item for item in data}

    # ------------------------------------------------------------------ #
    # Submit hours
    # ------------------------------------------------------------------ #

    def submit_hours(self, task_number: str, start_date: str, end_date: str,
                     logtime: str, note: str, company: str,
                     target_user_id: str = None, category: str = None,
                     task_data: dict = None) -> dict:
        uid = target_user_id or self.user_id
        cookies = {'cookies_are': 'working'}
        headers = {
            'Connection': 'keep-alive',
            'Accept': 'text/plain, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0',
            'Origin': BASE_URL,
        }

        if task_data:
            tb = task_data
            project_category = category or ''
        else:
            # Fetch projects list (used by regular single-user Submit Hours)
            today = datetime.today().strftime('%Y-%m-%d')
            projects_payload = (
                f'EndDate={today}&InclActivity=Y&InclAltRep=Y&InclCalls=Y&InclCallsCSR=Y'
                f'&InclOppTasks=Y&InclOppor=Y&InclQuotes=Y&InclTasksAssign=Y&InclTasksResp=Y'
                f'&_a=mytasklist_get&_pversion=d101&mobileflag=N&numdays=0&userid={uid}'
            )
            r4 = self.session.post(AJAX_URL, headers=headers, data=projects_payload,
                                   cookies=cookies, verify=False)
            projects = {item['resq_zoom_key']: item for item in json.loads(r4.text)['data']}
            tb = projects[task_number]

            try:
                project_category = tb.get('timebillcategory', '')
            except Exception:
                project_category = ''
            if category:
                project_category = category

        # Always fetch parent project number from the task page — required for
        # the Project field to populate correctly in Q360's Timebill Post Q view.
        open_payload = (
            f'_a=pageload&_navkey=1646064679867&_pversion=d101'
            f'&_referrer=action%3Dtask%26projectscheduleno%3D{task_number}%26_navkey%3D1646064679867'
            f'&_type=data&action=task&projectscheduleno={task_number}'
        )
        r5 = self.session.post(AJAX_URL, headers=headers, data=open_payload,
                               cookies=cookies, verify=False)
        try:
            temp = json.loads(r5.text)
            parent_project_no = temp['data']['data']['recordSet']['task']['data'][0]['parentprojectscheduleno']
        except (KeyError, IndexError, ValueError):
            parent_project_no = ''
        import sys as _sys
        print(f"  [pageload] task={task_number} uid={uid} parentprojectscheduleno={parent_project_no!r}",
              file=_sys.stderr, flush=True)

        if not task_data:
            try:
                cat_from_task = temp['data']['data']['recordSet']['task']['data'][0]['timebillcategory']
                if not project_category:
                    project_category = cat_from_task
            except (KeyError, IndexError):
                pass

        # Create timebill
        now = datetime.today()
        create_payload = (
            f'_a=timebill_create_fromtask&_pversion=d101'
            f'&date={now.strftime("%Y-%m-%d")}T{now.strftime("%H")}%3A{now.strftime("%M")}%3A{now.strftime("%S")}'
            f'&projectscheduleno={task_number}'
        )
        r6 = self.session.post(AJAX_URL, headers=headers, data=create_payload,
                               cookies=cookies, verify=False)
        timebill_no = json.loads(r6.text)['outvars']['timebillno']

        # Load timebill page
        load_payload = (
            f'_a=pageload&_pversion=d101'
            f'&_referrer=action%3Dtimebill%26timebillno%3D{timebill_no}'
            f'&_type=data&action=timebill&timebillno={timebill_no}'
        )
        self.session.post(AJAX_URL,
                          headers={'Content-Type': 'application/x-www-form-urlencoded'},
                          data=load_payload, cookies=cookies, verify=False)

        company_no = COMPANY_MAP.get(company.upper(), '01')
        moddate = now.strftime('%Y-%m-%d %H:%M:%S.000')
        loaddate = now.strftime('%Y-%m-%d %H:%M:%S')

        json_payload = {
            'blocktimeamount': '0.0000', 'blocktimeflag': 'Y',
            'blocktimehours': '0.00', 'blocktimeoverride': '',
            'category': project_category, 'comment': '',
            'companyno': company_no, 'customerno': tb['customerno'],
            'date': unquote(start_date), 'description': tb['description'],
            'dispatchno': '', 'endtime': unquote(end_date),
            'fixedamount': '0.0000', 'invoiceno': tb['invoiceno'],
            'logtime': logtime, 'moddate': moddate,
            'masterno': project_category, 'note': note,
            'opporno': tb['opporno'], 'payrollapproveflag': '',
            'pieceamount': '0.0000', 'piececount': '0.00',
            'projectno': tb['projectno'], 'projectscheduleno': task_number,
            'prtid': '', 'rate': '', 'serviceconitemno': '', 'subcat': '',
            'timebilled': logtime, 'timebillno': timebill_no,
            # Use the explicit target uid so bulk-on-behalf-of submissions
            # go to the right user, not to the project's default assignee.
            'userid': uid,
            'user1': '', 'user2': '', 'user3': '', 'user4': '',
            'user5': '', 'user6': '', 'user7': '0',
            'user8': '0.0000', 'user9': '0.0000', 'user10': '',
            'wagerate': '0.0000', 'wagetype': 'STANDARD',
            'companyname': tb['company'], 'company': tb['company'],
            'callno': '', 'problem': '', 'opportitle': '',
            'branch': tb['sitecity'], 'projecttitle': tb['projecttitle'],
            'username': uid, 'is_project_manager': 'n',
            'projecttasktitle': tb['description'], 'is_task_contact': 'y',
            'team_member': '', 'editaction': 'edit',
            'canmodify': 'y', 'candelete': 'y',
            'funnelopporno': '', 'qtyprodactual': '0',
            'qtyprodbudget': '0', 'qtyprodunit': '',
            'parentprojectscheduleno': parent_project_no,
            'loaddate': loaddate, 'currentuser': uid,
        }
        save_data = {
            '_a': 'timebill_save', '_hash': 'tab_timebill', '_pversion': 'd101',
            '_r': f'action=timebill&timebillno={timebill_no}',
            '_referrer': f'action=timebill&timebillno={timebill_no}&_navkey=1646070829830',
            'jsonRequest': json.dumps(json_payload),
            'timebillno': timebill_no,
        }
        import sys
        _source = 'bulk' if task_data else 'submit_hours'
        print(f"\n[Q360 timebill_save] source={_source} user={uid} task={task_number} timebillno={timebill_no}",
              file=sys.stderr, flush=True)
        print(f"  payload: {json.dumps(json_payload, indent=2)}", file=sys.stderr, flush=True)
        r7 = self.session.post(AJAX_URL,
                               headers={'Content-Type': 'application/x-www-form-urlencoded'},
                               data=urlencode(save_data, quote_via=quote_plus),
                               cookies=cookies, verify=False, timeout=25)
        print(f"  response: {r7.text[:500]}", file=sys.stderr, flush=True)
        # Surface Q360-level errors (response body may contain error details)
        try:
            resp_data = json.loads(r7.text)
            if isinstance(resp_data, dict):
                err = resp_data.get('error') or resp_data.get('message') or resp_data.get('msg')
                status = resp_data.get('status', '')
                if err or (status and str(status).lower() not in ('ok', 'success', '1', 'true', '')):
                    raise RuntimeError(f"Q360 rejected timebill: {err or resp_data}")
        except (json.JSONDecodeError, AttributeError):
            pass  # non-JSON response is not necessarily an error
        return {'status': 'ok', 'timebillno': timebill_no}

    # ------------------------------------------------------------------ #
    # Date helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def week_range_for_date(date_str: str) -> tuple[str, str]:
        """Return (monday, sunday) ISO strings for the week containing date_str."""
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        monday = d - timedelta(days=d.weekday())
        sunday = monday + timedelta(days=6)
        return str(monday), str(sunday)

    @staticmethod
    def _iso_week_num(date_str: str) -> str:
        yr, wk = datetime.strptime(date_str, '%Y-%m-%d').date().isocalendar()[:2]
        return f'{yr}{wk:02d}'

    @staticmethod
    def _week_dates(year: int, week: int):
        days = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                'Thursday': 4, 'Friday': 5, 'Saturday': 6, 'Sunday': 7}
        a = datetime.strptime(str(year), '%Y') + timedelta(days=7 * (week - 1))
        a += timedelta(days=7 - days.get(a.strftime('%A'), 0))
        return [(a + timedelta(days=k)).strftime('%Y-%m-%d') for k in range(7)]

    def _month_split(self, end_time_str: str):
        wn = self._iso_week_num(end_time_str[:10])
        week_list = self._week_dates(int(wn[:4]), int(wn[4:]))
        return [
            list(g)
            for _, g in groupby(week_list, key=lambda x: datetime.strptime(x, '%Y-%m-%d').month)
        ]

    @staticmethod
    def _is_admin_project(title: str) -> bool:
        return 'Internal Admin Project' in title or '2479' in title

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    def _parse_timebills(self, raw: str) -> list:
        data = json.loads(raw)['data']
        entries = []
        if data:
            for el in data:
                if el['date'] == '':
                    continue
                entries.append({
                    'startDate': el['date'],
                    'endDate': el['endtime'],
                    'hours': float(el['timebilled']),
                    'category': el['category'],
                    'project': el['title'],
                    'description': el['description'],
                    'company': el['company'],
                })
            entries.append(float(data[-1]['timebilled']))
        else:
            entries.append(0.0)
        return entries

    def _parse_dates(self, raw: str) -> list:
        data = json.loads(raw)['data']
        dates = []
        for el in data:
            if el['date'] == '':
                continue
            for m in self._month_split(el['endtime']):
                dates.append(f'{m[0]} to {m[-1]}')
            dates = list(dict.fromkeys(dates))
            dates.sort()
        return dates

    def _parse_weekly(self, raw: str) -> list:
        data = json.loads(raw)['data']
        tb: dict = {}
        if not data:
            return []

        for el in data:
            if el['date'] == '':
                continue
            key = el['description'] if self._is_admin_project(el['title']) else el['title']
            tb.setdefault(key, {})

        for el in data:
            if el['date'] == '':
                continue
            key = el['description'] if self._is_admin_project(el['title']) else el['title']
            for m in self._month_split(el['endtime']):
                tb[key].setdefault(f'{m[0]} to {m[-1]}', [])

        for el in data:
            if el['date'] == '':
                continue
            key = el['description'] if self._is_admin_project(el['title']) else el['title']
            for m in self._month_split(el['endtime']):
                if el['date'][:10] in m:
                    tb[key][f'{m[0]} to {m[-1]}'].append(float(el['timebilled']))

        for project in tb:
            for wr in tb[project]:
                tb[project][wr] = sum(tb[project][wr])
        return [tb]

    def _parse_weekly_total(self, raw: str) -> list:
        data = json.loads(raw)['data']
        tb: dict = {}
        if not data:
            return []

        for el in data:
            if el['date'] == '':
                continue
            for m in self._month_split(el['endtime']):
                tb.setdefault(f'{m[0]} to {m[-1]}', [])

        for el in data:
            if el['date'] == '':
                continue
            for m in self._month_split(el['endtime']):
                if el['date'][:10] in m:
                    wr = f'{m[0]} to {m[-1]}'
                    tb[wr].append(float(el['timebilled']))
                    tb = dict(sorted(tb.items()))

        return [{wr: sum(v) for wr, v in tb.items()}]

    def _parse_project_total(self, raw: str) -> dict:
        data = json.loads(raw)['data']
        tb: dict = {}
        if not data:
            return {}

        for el in data:
            if el['date'] == '':
                continue
            key = el['description'] if self._is_admin_project(el['title']) else el['title']
            wn = self._iso_week_num(el['endtime'][:10])
            week_list = self._week_dates(int(wn[:4]), int(wn[4:]))
            wr = f'{week_list[0]} to {week_list[-1]}'
            tb.setdefault(key, {}).setdefault(wr, []).append(float(el['timebilled']))
            tb[key] = dict(sorted(tb[key].items()))
            tb = dict(sorted(tb.items()))

        result = {}
        for project, weeks in tb.items():
            result[project] = sum(sum(v) for v in weeks.values())
        return result
