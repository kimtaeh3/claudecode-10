import copy
import csv
from datetime import datetime
import pandas
from flask import Flask, request, render_template, session, redirect, url_for, flash
from flask_login import UserMixin, LoginManager
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length
import json
import sqlite3
from decouple import config

from q360script import q360script

app = Flask(__name__)
app.secret_key = config('SECRET_KEY', default='change-me-in-production')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin):
    def __init__(self, username):
        self.name = username

    @property
    def id(self):
        return self.name


class LoginForm(FlaskForm):
    userID = StringField(validators=[InputRequired(), Length(min=3, max=20)])
    password = PasswordField(validators=[InputRequired(), Length(min=3, max=20)])
    submit = SubmitField("Login")


# **************************** APP ROUTING *****************************************

@app.route('/')
def homePage():
    return render_template("home.html", loginVal=bool(session.get('account')))


@app.route('/dashboard')
def dashboard():
    return render_template("landing_page.html", loginVal=bool(session.get('account')))


@app.route('/login', methods=["GET", "POST"])
def login():
    if session.get('account'):
        return redirect(url_for('homePage'))

    form = LoginForm()
    if form.validate_on_submit():
        user_id = form.userID.data
        password = form.password.data
        Q360 = q360script()
        data = json.loads(Q360.login(user_id, password))
        if data["success"]:
            session['account'] = {"userID": user_id, "password": password}
            return redirect(url_for('homePage'))

    return render_template("login.html", form=form, loginVal=bool(session.get('account')))


@app.route('/logout', methods=['GET'])
def logout():
    if session.get('account'):
        session['account'] = None
        return redirect(url_for('homePage'))
    return redirect(url_for('login'))


@app.route('/viewhours', methods=["GET", "POST"])
def viewhours():
    if session.get('account'):
        return render_template("index.html", loginVal=bool(session.get('account')))
    return redirect(url_for('login'))


# ********************** ALL USERID SEARCH *************************************

@app.route('/getHoursForAllForWeek', methods=['GET'])
def getHoursForAllForWeek():
    Q360 = q360script()
    with open('accounts.csv', 'r') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)
        for line in csv_reader:
            Q360.returnUserInfoForWeek(line[0])
    return json.dumps(Q360.employeeHours)


@app.route('/getHoursForAllForMonth', methods=['GET'])
def getHoursForAllForMonth():
    Q360 = q360script()
    with open('accounts.csv', 'r') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)
        for line in csv_reader:
            Q360.returnUserInfoForMonth(line[0])
    return json.dumps(Q360.employeeHours)


# ********************** SINGLE USERID SEARCH - JSON ****************************

@app.route('/getHoursForWeek', methods=['GET'])
def getHoursForWeek():
    Q360 = q360script()
    user_id = request.args.get('user', default="", type=str)
    Q360.returnUserInfoForWeek(user_id)
    result = copy.deepcopy(Q360.employeeHours)
    Q360.employeeHours.clear()
    return json.dumps(result)


@app.route('/getHoursForMonth', methods=['GET'])
def getHoursForMonth():
    Q360 = q360script()
    user_id = request.args.get('user', default="", type=str)
    Q360.returnUserInfoForMonth(user_id)
    return json.dumps(Q360.employeeHours[user_id])


# ********************** FORECASTING ********************************************

@app.route('/forecasting', methods=['GET'])
def forecasting():
    user_id = session.get('account')['userID']
    connection = sqlite3.connect('q360test_db.db')
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    db_call = cursor.execute(
        "SELECT forecast_id, progress, task_id, customer, sow, utilization, project_name, team, "
        "(SELECT full_name from user WHERE user_id = pm) as pm, "
        "(SELECT full_name from user WHERE user_id = team_lead) as team_lead, "
        "sub_org, cost, (SELECT full_name from user WHERE user_id = resources) as resources, "
        "role, hrs_rate, perc, alloc, con, forecast, rem "
        "FROM forecast WHERE resources = (SELECT user_id FROM user WHERE username = ?)",
        (user_id,)
    )
    db_result = db_call.fetchall()
    for row in db_result:
        row.keys()
    return render_template('forecasting.html', userID=user_id, forecasting=db_result)


# ********************** SINGLE USERID SEARCH - HTML ****************************

@app.route('/getTableForCustom', methods=['GET'])
def getTableForCustom():
    if not session.get('account'):
        return redirect(url_for('login'))

    user_id = request.args.get('user', default="", type=str)
    team = request.args.get('teams', default="", type=str)
    start_date = request.args.get('start', default="", type=str)
    end_date = request.args.get('end', default="", type=str)
    session['team'] = team

    if team == "Single":
        Q360 = q360script()
        Q360.returnUserInfoForCustomTable(user_id, start_date, end_date, team)
        result = copy.deepcopy(Q360.employeeHours)
        Q360.employeeHours.clear()

        project_names = [v["description"] for v in Q360.getProjects(user_id).values()]

        return render_template(
            "view_hours.html",
            content=result[user_id],
            userId=user_id,
            startDate=start_date,
            endDate=end_date,
            projectsList=project_names,
            loginVal=bool(session.get('account')),
            weeklyReport=1,
        )
    else:
        Q360 = q360script()
        with open('accounts.csv', 'r') as csv_file:
            csv_reader = csv.reader(csv_file)
            next(csv_reader)
            for line in csv_reader:
                if line[1] == team:
                    Q360.returnUserInfoForCustomTable(line[0], start_date, end_date, team)

        result = copy.deepcopy(Q360.employeeHours)
        Q360.employeeHours.clear()
        return render_template(
            "teamTable.html",
            content=result,
            userId=user_id,
            startDate=start_date,
            endDate=end_date,
            loginVal=bool(session.get('account')),
            weeklyReport=1,
        )


@app.route('/weekly-report', methods=["POST", "GET"])
def weeklyReport():
    if not session.get('account'):
        return redirect(url_for('login'))

    if "team" not in session:
        return redirect("/")

    team = session["team"]
    Q360 = q360script()
    with open('accounts.csv', 'r') as csv_file:
        csv_reader = csv.reader(csv_file)
        next(csv_reader)
        for line in csv_reader:
            if line[1] == team:
                Q360.returnUserInfoForWeek(line[0])

    first_user = list(Q360.employeeHours.keys())[0]
    start_date = Q360.employeeHours[first_user]["timePeriod"]["start"]
    end_date = Q360.employeeHours[first_user]["timePeriod"]["end"]
    result = copy.deepcopy(Q360.employeeHours)
    Q360.employeeHours.clear()

    if request.method == "POST":
        for user in result:
            if result[user]["totalHours"] < 40:
                Q360.sendMail(
                    str(user),
                    float(result[user]["totalHours"]),
                    str(result[user]["timePeriod"]["start"]),
                    str(result[user]["timePeriod"]["end"]),
                )

    return render_template(
        "weeklyReport.html",
        content=result,
        startDate=str(start_date),
        endDate=str(end_date),
        teamLead=team,
        loginVal=bool(session.get('account')),
    )


@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if not session.get('account'):
        return redirect(url_for('login'))

    Q360 = q360script()
    projects_list = Q360.getProjects()
    new_project_list = [[v["description"], k] for k, v in projects_list.items()][1:]

    categories = [
        "CABLE - INSTALL 1", "CABLE - INSTALL 2", "CABLE - INSTALL 3", "CABLE - PM",
        "DATA - NTWKARCH", "DATA - NTWKTECH", "DATA - PM", "HELPDESK",
        "VOICE - PM", "VOICE - UCCONSULT", "VOICE - UCCINSTALL", "VOICE - UCCSUPPORT",
        "VOICE - UCCSYSDS", "VOICE- CCAPPDEV", "VOICE- CCARCH", "VOICE- CCBA",
        "VOICE- CCBC", "VOICE- CCINT", "VOICE- CCPM", "VOICE- CCTEST",
        "TRAVEL", "ON-CALL", "ADMIN", "HOLIDAY", "PTO", "VACATION",
    ]
    companies = [
        "CONNEX TELECOMMUNICATIONS INC.", "CONNEX QUEBEC INC.",
        "PULSE SERVICES INC.", "CONNEX USA",
    ]

    return render_template(
        "submit.html",
        loginVal=bool(session.get('account')),
        projectsList=new_project_list,
        categoryList=categories,
        companyList=companies,
        userID=session['account']['userID'],
    )


@app.route('/submit/<userID>', methods=['GET', 'POST'])
def submitOnBehalf(userID):
    if session.get('account') and session['account']['userID'] == "demoq360billing":
        Q360 = q360script()
        projects_list = Q360.getProjects(userID)
        new_project_list = [[v["description"], k] for k, v in projects_list.items()][1:]

        categories = [
            "CABLE - INSTALL 1", "CABLE - INSTALL 2", "CABLE - INSTALL 3", "CABLE - PM",
            "DATA - NTWKARCH", "DATA - NTWKTECH", "DATA - PM", "HELPDESK",
            "VOICE - PM", "VOICE - UCCONSULT", "VOICE - UCCINSTALL", "VOICE - UCCSUPPORT",
            "VOICE - UCCSYSDS", "VOICE- CCAPPDEV", "VOICE- CCARCH", "VOICE- CCBA",
            "VOICE- CCBC", "VOICE- CCINT", "VOICE- CCPM", "VOICE- CCTEST",
            "TRAVEL", "ON-CALL", "ADMIN", "HOLIDAY", "PTO", "VACATION",
        ]
        companies = [
            "CONNEX TELECOMMUNICATIONS INC.", "CONNEX QUEBEC INC.",
            "PULSE SERVICES INC.", "CONNEX USA",
        ]

        return render_template(
            "submit.html",
            loginVal=bool(session.get('account')),
            projectsList=new_project_list,
            categoryList=categories,
            companyList=companies,
            userID=session['account']['userID'],
            userSearched=userID,
        )
    elif session.get('account'):
        return redirect(url_for('submit'))
    return redirect(url_for('login'))


@app.route('/submithours', methods=['GET', 'POST'])
def submithours():
    if not session.get('account'):
        return redirect(url_for('login'))

    task_number = request.args.get('projects', default="", type=str)
    entry = request.args.get('entry_option', default="", type=str)
    day_switch = request.args.get('toggle', default="", type=str)

    is_admin = session['account']['userID'] == "demoq360billing"
    user_id = request.args.get('userID', default=None, type=str) if is_admin else None
    category = request.args.get('category', default=None, type=str) if is_admin else None
    note = request.args.get('note', default="", type=str)
    company = request.args.get('company', default="", type=str)
    weekends_option = request.args.get('weekends', default="", type=bool)

    Q360 = q360script()

    if day_switch == "on":
        start_date = request.args.get('start', default="", type=str)
        start_time = request.args.get('startTime', default="", type=str)
        end_date = request.args.get('end', default="", type=str)
        end_time = request.args.get('endTime', default="", type=str)

        start = f"{start_date}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
        end = f"{end_date}%20{end_time[:2]}%3A{end_time[3:5]}%3A00.000"
        start_dt = datetime.strptime(f"{start_date} {start_time}", '%Y-%m-%d %H:%M')
        end_dt = datetime.strptime(f"{end_date} {end_time}", '%Y-%m-%d %H:%M')
        delta = end_dt - start_dt
        log = f"{str(delta)[:-6]}.{str(delta)[-5:-3]}"

        if entry == "Single":
            Q360.submitHours(task_number, start, end, log, note, company, user_id, category)
        elif entry == "Multiple":
            days_list = (
                pandas.date_range(start_date, end_date)
                if weekends_option
                else pandas.bdate_range(start_date, end_date, freq='B')
            )
            for day in days_list.strftime("%Y-%m-%d"):
                s = f"{day}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
                e = f"{day}%20{end_time[:2]}%3A{end_time[3:5]}%3A00.000"
                sd = datetime.strptime(f"{day} {start_time}", '%Y-%m-%d %H:%M')
                ed = datetime.strptime(f"{day} {end_time}", '%Y-%m-%d %H:%M')
                d = ed - sd
                lg = f"{str(d)[:-6]}.{str(d)[-5:-3]}"
                Q360.submitHours(task_number, s, e, lg, note, company, user_id, category)
    else:
        start_date = request.args.get('start2', default="", type=str)
        start_time = request.args.get('startTime2', default="", type=str)
        end_date = request.args.get('end2', default="", type=str)
        hours_log = int(request.args.get('hoursLog', default="0", type=str))

        start1 = f"{start_date}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
        end_hour1 = str(int(start_time[:2]) + min(hours_log, 4))
        end_time1 = f"{end_hour1}:{start_time[3:5]}"
        end1 = f"{end_date}%20{end_hour1.zfill(2)}%3A{start_time[3:5]}%3A00.000"
        sd1 = datetime.strptime(f"{start_date} {start_time}", '%Y-%m-%d %H:%M')
        ed1 = datetime.strptime(f"{end_date} {end_time1}", '%Y-%m-%d %H:%M')
        delta1 = ed1 - sd1
        log1 = f"{str(delta1)[:-6]}.{str(delta1)[-5:-3]}"

        if hours_log > 4:
            start_hour2 = str(int(start_time[:2]) + 5)
            start2 = f"{start_date}%20{start_hour2}%3A{start_time[3:5]}%3A00.000"
            end_hour2 = str(int(start_time[:2]) + hours_log + 1)
            end_time2 = f"{end_hour2}:{start_time[3:5]}"
            end2 = f"{end_date}%20{end_hour2.zfill(2)}%3A{end_time2[3:5]}%3A00.000"
            sd2 = datetime.strptime(f"{start_date} {start_hour2}:{start_time[3:5]}", '%Y-%m-%d %H:%M')
            ed2 = datetime.strptime(f"{end_date} {end_time2}", '%Y-%m-%d %H:%M')
            delta2 = ed2 - sd2
            log2 = f"{str(delta2)[:-6]}.{str(delta2)[-5:-3]}"

        if entry == "Single":
            Q360.submitHours(task_number, start1, end1, log1, note, company, user_id, category)
            if hours_log > 4:
                Q360.submitHours(task_number, start2, end2, log2, note, company, user_id, category)
        elif entry == "Multiple":
            days_list = (
                pandas.date_range(start_date, end_date)
                if weekends_option
                else pandas.bdate_range(start_date, end_date, freq='B')
            )
            for day in days_list.strftime("%Y-%m-%d"):
                s = f"{day}%20{start_time[:2]}%3A{start_time[3:5]}%3A00.000"
                e = f"{day}%20{end_hour1.zfill(2)}%3A{end_time1[3:5]}%3A00.000"
                sd = datetime.strptime(f"{day} {start_time}", '%Y-%m-%d %H:%M')
                ed = datetime.strptime(f"{day} {end_time1}", '%Y-%m-%d %H:%M')
                d = ed - sd
                lg = f"{str(d)[:-6]}.{str(d)[-5:-3]}"
                Q360.submitHours(task_number, s, e, lg, note, company, user_id, category)

            if hours_log > 4:
                for day in days_list.strftime("%Y-%m-%d"):
                    s = f"{day}%20{start_hour2}%3A{start_time[3:5]}%3A00.000"
                    e = f"{day}%20{end_hour2.zfill(2)}%3A{end_time2[3:5]}%3A00.000"
                    sd = datetime.strptime(f"{day} {start_hour2}:{start_time[3:5]}", '%Y-%m-%d %H:%M')
                    ed = datetime.strptime(f"{day} {end_time2}", '%Y-%m-%d %H:%M')
                    d = ed - sd
                    lg = f"{str(d)[:-6]}.{str(d)[-5:-3]}"
                    Q360.submitHours(task_number, s, e, lg, note, company, user_id, category)

    flash('Successfully Created Entries!')
    return redirect(url_for('submit'))


# **************************** ERROR HANDLING *********************************

@app.errorhandler(Exception)
def page_not_found(error):
    code = error.code
    return render_template(
        'error_handling.html',
        loginVal=bool(session.get('account')),
        code=code,
        name=error.name,
        description=error.description,
    ), code


if __name__ == "__main__":
    app.run()
