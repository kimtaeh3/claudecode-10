from flask import session
import requests
import json
import smtplib
from decouple import config
from datetime import datetime, timedelta
from itertools import groupby
from urllib.parse import urlencode, quote_plus, unquote


class q360script:
    # employeeHours: Dictionary containing key of userID and value of total weekly hours.
    # FORMAT:
    # {
    #   "timePeriod": {"start": ..., "end": ...},
    #   "totalHours": 80.0,
    #   "userReport": [{"category", "description", "endDate", "hours", "project", "startDate", "company"}],
    #   "date": [week1, week2],
    #   "weeklyUserReport": [{"project": {"weekRange": totalHours}}],
    #   "weeklyTotalReport": [{"weekRange": totalHours}],
    #   "projectTotalReport": {"project": totalHours}
    # }

    def __init__(self):
        self.employeeHours = {}

    # **************************** DATE FUNCTIONS *****************************************

    def returnUserInfoForCustomTable(self, userId, startDate, endDate, team):
        self.returnUserInfo(userId, startDate, endDate, team)

    def returnUserInfoForMonth(self, userId):
        endDate = datetime.date(datetime.now())
        startDate = endDate - timedelta(weeks=4)
        self.returnUserInfo(userId, str(startDate), str(endDate))

    def returnUserInfoForWeek(self, userId):
        endDate = datetime.date(datetime.now())
        startDate = endDate - timedelta(days=4)
        self.returnUserInfo(userId, str(startDate), str(endDate))

    def returnWeeks(self, year, week):
        days = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                'Thursday': 4, 'Friday': 5, 'Saturday': 6, 'Sunday': 7}
        a = datetime.strptime(f'{year}', '%Y') + timedelta(days=7 * (week - 1))
        a += timedelta(days=7 - days.get(a.strftime('%A'), 0))
        for k in range(7):
            yield (a + timedelta(days=k)).strftime('%Y-%m-%d')

    def returnWeekNum(self, start):
        year_week_raw = datetime.strptime(start, '%Y-%m-%d').date().isocalendar()[:2]
        return '{}{:02}'.format(*year_week_raw)

    # **************************** AUTHENTICATION HELPER ****************************

    def _get_authenticated_session(self):
        url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action=login'
        cookies = {'cookies_are': 'working'}
        header = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://websupport.connexservice.ca/controller.php?action=login',
        }
        files = {
            'jsonRequest': '{{"userid": "{}","password": "{}","touch":"false"}}'.format(
                session['account']['userID'], session['account']['password']
            )
        }
        s = requests.Session()
        s.get('https://websupport.connexservice.ca/controller.php?action=login', cookies=cookies, verify=False)
        s.post(url, headers=header, data=files, cookies=cookies, verify=False)
        return s, cookies, header

    # **************************** MAIN FUNCTIONS *****************************************

    def login(self, user_id, password):
        url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action=login'
        cookies = {'cookies_are': 'working'}
        header = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://websupport.connexservice.ca/controller.php?action=login',
        }
        files = {'jsonRequest': f'{{"userid": "{user_id}","password": "{password}","touch":"false"}}'}
        s = requests.Session()
        s.get('https://websupport.connexservice.ca/controller.php?action=login', cookies=cookies, verify=False)
        r = s.post(url, headers=header, data=files, cookies=cookies, verify=False)
        return r.text

    def returnUserInfo(self, user_id, start_date, end_date, team="Single"):
        s, cookies, header = self._get_authenticated_session()

        url2 = 'https://websupport.connexservice.ca/ajax/'
        files2 = {
            "userid": user_id,
            "startdate": start_date,
            "enddate": end_date,
            "_a": "get_timebill_byuseriddetail",
        }
        r = s.post(url2, headers=header, data=files2, cookies=cookies, verify=False)

        user_report = self.parseJson(r.text)
        weekly_user_report = self.parseJsonWeekly(r.text)
        weekly_total_report = self.parseJsonWeeklyTotal(r.text)
        project_total_report = self.parseJsonProjectTotal(r.text)
        date = self.parseListDates(r.text)
        total_hours = user_report[-1]
        del user_report[-1]

        self.employeeHours[user_id] = {
            "timePeriod": {"start": start_date, "end": end_date},
            "totalHours": total_hours,
            "userReport": user_report,
            "date": date,
            "weeklyUserReport": weekly_user_report,
            "weeklyTotalReport": weekly_total_report,
            "projectTotalReport": project_total_report,
        }
        return r.text

    def parseJson(self, json_string):
        data = json.loads(json_string)
        user_report = []

        if data["data"]:
            for element in data["data"]:
                if element["date"] == "":
                    continue
                timebill = {
                    "startDate": element["date"],
                    "endDate": element["endtime"],
                    "hours": float(element["timebilled"]),
                    "category": element["category"],
                    "project": element["title"],
                    "description": element["description"],
                    "company": element["company"],
                }
                user_report.append(timebill)
            total_hours = float(data["data"][-1]["timebilled"])
            user_report.append(total_hours)
        else:
            user_report.append(0)

        return user_report

    def parseListDates(self, json_string):
        data = json.loads(json_string)
        date = []

        if not data["data"]:
            return date

        for elem in data['data']:
            if elem["date"] == "":
                continue
            end_date = elem['endtime'][:10]
            week_num = self.returnWeekNum(end_date)
            week_list = list(self.returnWeeks(int(week_num[:4]), int(week_num[4:])))
            month_split = [
                list(l)
                for k, l in groupby(week_list, key=lambda x: datetime.strptime(x, "%Y-%m-%d").month)
            ]
            for m in month_split:
                week_range = f"{m[0]} to {m[-1]}"
                date.append(week_range)
            date = list(dict.fromkeys(date))
            date.sort()

        return date

    def _get_month_split(self, end_time_str):
        end_date = end_time_str[:10]
        week_num = self.returnWeekNum(end_date)
        week_list = list(self.returnWeeks(int(week_num[:4]), int(week_num[4:])))
        return [
            list(l)
            for k, l in groupby(week_list, key=lambda x: datetime.strptime(x, "%Y-%m-%d").month)
        ]

    def _is_admin_project(self, title):
        return "Internal Admin Project" in title or "2479" in title

    def parseJsonWeekly(self, json_string):
        data = json.loads(json_string)
        weekly_timebill = {}

        if not data["data"]:
            return []

        # Pass 1: initialize project keys
        for elem in data['data']:
            if elem["date"] == "":
                continue
            key = elem['description'] if self._is_admin_project(elem['title']) else elem['title']
            weekly_timebill[key] = {}

        # Pass 2: initialize week range keys
        for elem in data['data']:
            if elem["date"] == "":
                continue
            month_split = self._get_month_split(elem['endtime'])
            key = elem['description'] if self._is_admin_project(elem['title']) else elem['title']
            for m in month_split:
                week_range = f"{m[0]} to {m[-1]}"
                weekly_timebill[key][week_range] = []

        # Pass 3: fill hours
        for elem in data['data']:
            if elem["date"] == "":
                continue
            month_split = self._get_month_split(elem['endtime'])
            key = elem['description'] if self._is_admin_project(elem['title']) else elem['title']
            for m in month_split:
                if elem["date"][:10] in m:
                    week_range = f"{m[0]} to {m[-1]}"
                    weekly_timebill[key][week_range].append(float(elem['timebilled']))

        for project in weekly_timebill:
            for week_range in weekly_timebill[project]:
                weekly_timebill[project][week_range] = sum(weekly_timebill[project][week_range])

        return [weekly_timebill]

    def parseJsonWeeklyTotal(self, json_string):
        data = json.loads(json_string)
        weekly_timebill = {}

        if not data["data"]:
            return []

        for elem in data['data']:
            if elem["date"] == "":
                continue
            for m in self._get_month_split(elem['endtime']):
                week_range = f"{m[0]} to {m[-1]}"
                weekly_timebill[week_range] = []

        for elem in data['data']:
            if elem["date"] == "":
                continue
            for m in self._get_month_split(elem['endtime']):
                if elem["date"][:10] in m:
                    week_range = f"{m[0]} to {m[-1]}"
                    weekly_timebill[week_range].append(float(elem['timebilled']))
                    weekly_timebill = dict(sorted(weekly_timebill.items()))

        for week_range in weekly_timebill:
            weekly_timebill[week_range] = sum(weekly_timebill[week_range])

        return [weekly_timebill]

    def parseJsonProjectTotal(self, json_string):
        data = json.loads(json_string)
        weekly_timebill = {}
        project_total_report = {}

        if not data["data"]:
            return project_total_report

        # Init project keys
        for elem in data['data']:
            if elem["date"] == "":
                continue
            key = elem['description'] if self._is_admin_project(elem['title']) else elem['title']
            weekly_timebill[key] = {}

        # Fill hours by week range
        for elem in data['data']:
            if elem["date"] == "":
                continue
            key = elem['description'] if self._is_admin_project(elem['title']) else elem['title']
            week_num = self.returnWeekNum(elem['endtime'][:10])
            week_list = list(self.returnWeeks(int(week_num[:4]), int(week_num[4:])))
            week_range = f"{week_list[0]} to {week_list[-1]}"
            weekly_timebill[key].setdefault(week_range, [])
            weekly_timebill[key][week_range].append(float(elem['timebilled']))
            weekly_timebill[key] = dict(sorted(weekly_timebill[key].items()))
            weekly_timebill = dict(sorted(weekly_timebill.items()))

        for project in weekly_timebill:
            for week_range in weekly_timebill[project]:
                weekly_timebill[project][week_range] = sum(weekly_timebill[project][week_range])

        for project, weeks in weekly_timebill.items():
            project_total_report[project] = sum(weeks.values())

        return project_total_report

    def sendMail(self, user_id, total_hours, start_date, end_date):
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(config('EMAIL_ADDRESS'), config('EMAIL_PASSWORD'))
        subject = f"Subject: Weekly Timesheet Reminder: {start_date} - {end_date} \n\n"
        body = (
            f"You have completed {total_hours} hours this week. "
            "Please update your hours on Q360."
        )
        server.sendmail(config('EMAIL_ADDRESS'), f"{user_id}@connexservice.ca", subject + body)
        server.quit()

    def getProjects(self, user_id=None):
        s, cookies, _ = self._get_authenticated_session()

        uid = user_id if user_id else session['account']['userID']
        today = datetime.today().strftime('%Y-%m-%d')
        payload = (
            f"EndDate={today}&InclActivity=Y&InclAltRep=Y&InclCalls=Y&InclCallsCSR=Y"
            f"&InclOppTasks=Y&InclOppor=Y&InclQuotes=Y&InclTasksAssign=Y&InclTasksResp=Y"
            f"&_a=mytasklist_get&_pversion=d101&mobileflag=N&numdays=0&userid={uid}"
        )
        headers = {
            'Connection': 'keep-alive',
            'Accept': 'text/plain, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': 'https://websupport.connexservice.ca',
            'Referer': 'https://websupport.connexservice.ca/controller.php?action=mytasklist',
        }
        r = s.post("https://websupport.connexservice.ca/ajax/", headers=headers, data=payload, cookies=cookies, verify=False)
        return self.parseProjects(r.text)

    def submitHours(self, task_number, start_date, end_date, logtime, note, company, user_id=None, category=None):
        s, cookies, _ = self._get_authenticated_session()

        uid = user_id if user_id else session['account']['userID']
        today = datetime.today().strftime('%Y-%m-%d')
        payload = (
            f"EndDate={today}&InclActivity=Y&InclAltRep=Y&InclCalls=Y&InclCallsCSR=Y"
            f"&InclOppTasks=Y&InclOppor=Y&InclQuotes=Y&InclTasksAssign=Y&InclTasksResp=Y"
            f"&_a=mytasklist_get&_pversion=d101&mobileflag=N&numdays=0&userid={uid}"
        )
        common_headers = {
            'Connection': 'keep-alive',
            'Accept': 'text/plain, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': 'https://websupport.connexservice.ca',
        }
        ajax_url = "https://websupport.connexservice.ca/ajax/"

        r4 = s.post(ajax_url, headers=common_headers, data=payload, cookies=cookies, verify=False)
        projects_list = self.parseProjects(r4.text)

        # Open task page
        open_payload = (
            f"_a=pageload&_navkey=1646064679867&_pversion=d101"
            f"&_referrer=action%3Dtask%26projectscheduleno%3D{task_number}%26_navkey%3D1646064679867"
            f"&_type=data&action=task&projectscheduleno={task_number}"
        )
        r5 = s.post(ajax_url, headers=common_headers, data=open_payload, cookies=cookies, verify=False)
        temp = json.loads(r5.text)

        try:
            parent_project_no = temp["data"]["data"]["recordSet"]["task"]["data"][0]["parentprojectscheduleno"]
        except (KeyError, IndexError):
            parent_project_no = ""

        try:
            project_category = temp["data"]["data"]["recordSet"]["task"]["data"][0]["timebillcategory"]
        except (KeyError, IndexError):
            project_category = ""

        if category:
            project_category = category

        # Create timebill
        now = datetime.today()
        create_payload = (
            f"_a=timebill_create_fromtask&_pversion=d101"
            f"&date={now.strftime('%Y-%m-%d')}T{now.strftime('%H')}%3A{now.strftime('%M')}%3A{now.strftime('%S')}"
            f"&projectscheduleno={task_number}"
        )
        r6 = s.post(ajax_url, headers=common_headers, data=create_payload, cookies=cookies, verify=False)
        timebill_no = json.loads(r6.text)["outvars"]["timebillno"]

        # Load timebill page
        load_payload = (
            f"_a=pageload&_pversion=d101"
            f"&_referrer=action%3Dtimebill%26timebillno%3D{timebill_no}"
            f"&_type=data&action=timebill&timebillno={timebill_no}"
        )
        s.post(ajax_url, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=load_payload, cookies=cookies, verify=False)

        company_map = {
            "CONNEX QUEBEC INC.": "02",
            "PULSE SERVICES INC.": "03",
            "CONNEX USA": "04",
        }
        company_no = company_map.get(company.upper(), "01")

        timebill_dict = projects_list[task_number]
        moddate = now.strftime('%Y-%m-%d %H:%M:%S.000')
        loaddate = now.strftime('%Y-%m-%d %H:%M:%S')

        json_payload = {
            "blocktimeamount": "0.0000",
            "blocktimeflag": "Y",
            "blocktimehours": "0.00",
            "blocktimeoverride": "",
            "category": project_category,
            "comment": "",
            "companyno": company_no,
            "customerno": timebill_dict["customerno"],
            "date": unquote(start_date),
            "description": timebill_dict["description"],
            "dispatchno": "",
            "endtime": unquote(end_date),
            "fixedamount": "0.0000",
            "invoiceno": timebill_dict["invoiceno"],
            "logtime": logtime,
            "moddate": moddate,
            "masterno": project_category,
            "note": note,
            "opporno": timebill_dict["opporno"],
            "payrollapproveflag": "",
            "pieceamount": "0.0000",
            "piececount": "0.00",
            "projectno": timebill_dict["projectno"],
            "projectscheduleno": task_number,
            "prtid": "",
            "rate": "",
            "serviceconitemno": "",
            "subcat": "",
            "timebilled": logtime,
            "timebillno": timebill_no,
            "userid": timebill_dict["assignee"],
            "user1": "", "user2": "", "user3": "", "user4": "",
            "user5": "", "user6": "", "user7": "0",
            "user8": "0.0000", "user9": "0.0000", "user10": "",
            "wagerate": "0.0000",
            "wagetype": "STANDARD",
            "companyname": timebill_dict["company"],
            "company": timebill_dict["company"],
            "callno": "",
            "problem": "",
            "opportitle": "",
            "branch": timebill_dict["sitecity"],
            "projecttitle": timebill_dict["projecttitle"],
            "username": timebill_dict["assignee"],
            "is_project_manager": "n",
            "projecttasktitle": timebill_dict["description"],
            "is_task_contact": "y",
            "team_member": "",
            "editaction": "edit",
            "canmodify": "y",
            "candelete": "y",
            "funnelopporno": "",
            "qtyprodactual": "0",
            "qtyprodbudget": "0",
            "qtyprodunit": "",
            "parentprojectscheduleno": parent_project_no,
            "loaddate": loaddate,
            "currentuser": timebill_dict["assignee"],
        }

        payload_data = {
            "_a": "timebill_save",
            "_hash": "tab_timebill",
            "_pversion": "d101",
            "_r": f"action=timebill&timebillno={timebill_no}",
            "_referrer": f"action=timebill&timebillno={timebill_no}&_navkey=1646070829830",
            "jsonRequest": json.dumps(json_payload),
            "timebillno": timebill_no,
        }
        final_payload = urlencode(payload_data, quote_via=quote_plus)
        s.post(ajax_url, headers={'Content-Type': 'application/x-www-form-urlencoded'}, data=final_payload, cookies=cookies, verify=False)

        return json.loads(r5.text)

    def parseProjects(self, json_string):
        temp = json.loads(json_string)["data"]
        return {item["resq_zoom_key"]: item for item in temp}
