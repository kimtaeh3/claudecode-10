import requests
import json
import smtplib
import csv
from decouple import config
from datetime import datetime, timedelta
from flask import Flask, request, render_template
from flask_ngrok import run_with_ngrok

app = Flask(__name__)
run_with_ngrok(app)


# employeeHours: Dictionary containing key of userID and value of total weekly hours.
# @PARAMS:
# 1) timePeriod = contains a "start" and "end" key which contain the values of
# the start and end dates of the requested time period.
# 2) totalHours =
# total hours for the requested time period.
# 3) userReport = a list containing the individual time bills for the
# requested period, shows category, description, endDate, hours, project, and startDate.

# FORMAT:

# {
# "timePeriod":
#   {
#    "start":
#    "end":
#   }
# "totalHours": 80.0,
# "userReport":
#  [
#     {
#       "category":
#       "description":
#       "endDate":
#       "hours":
#       "project":
#       "startDate":
#     }
#   ]
# }

employeeHours = {
}


# **************************** DATE FUNCTIONS *****************************************
# *************************************************************************************

# Custom startDate and endDate
def returnUserInfoForCustom(userId):
    endDate = "2021-12-17"
    startDate = "2021-12-06"
    returnUserInfo(userId, startDate, endDate)


# Monthly startDate and endDate: run on the last Friday of the month
def returnUserInfoForMonth(userId):
    endDate = datetime.date(datetime.now())  # Friday
    startDate = endDate - timedelta(weeks=4)  # Monday
    returnUserInfo(userId, str(startDate), str(endDate))


# Weekly startDate and endDate: run on the last Friday of the week
def returnUserInfoForWeek(userId):
    endDate = datetime.date(datetime.now())  # Friday
    startDate = endDate - timedelta(days=4)  # Monday
    returnUserInfo(userId, str(startDate), str(endDate))


# **************************** MAIN FUNCTIONS *****************************************
# *************************************************************************************

def returnUserInfo(userId, startDate, endDate):
    # print("userId:", userId)

    url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action%3Dlogin'
    cookies = dict(cookies_are='working')

    header = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
              'X-Requested-With': 'XMLHttpRequest',
              'Referer': 'https://websupport.connexservice.ca/controller.php?action=login'}
    url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action=login'

    files = {'jsonRequest': '{"userid": "%s","password": "%s","touch":"false"}' % (
        config('Q360_USERID'), config('Q360_PASSWORD'))}

    s = requests.Session()
    r2 = s.get('https://websupport.connexservice.ca/controller.php?action=login', cookies=cookies, verify=False)
    r = s.post(url, headers=header, data=files, cookies=cookies, verify=False)

    url2 = 'https://websupport.connexservice.ca/ajax/'
    files2 = {"userid": userId, "startdate": startDate, "enddate": endDate,
              "_a": "get_timebill_byuseriddetail"}
    r = s.post(url2, headers=header, data=files2, cookies=cookies, verify=False)

    url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action%3Dlogin%27'

    userReport = parseJson(r.text)  # Converts employee timesheet text to JSON
    totalHours = userReport[len(userReport) - 1]
    del userReport[-1]  # Removes the last element of userReport. The total.
    employeeHours[userId] = {
        "timePeriod": {"start": startDate, "end": endDate},
        "totalHours": totalHours,
        "userReport": userReport
    }
    # sendMail(totalHours, userId, startDate, endDate)  # Send mail function
    return r.text


# This function parses the text from the Q360 API to JSON Format
def parseJson(jsonString):
    data = json.loads(jsonString)
    userReport = []

    if len(data["data"]) > 0:
        for element in data["data"]:
            if element["date"] == "":
                continue
            timebill = {
                "startDate": element["date"],
                "endDate": element["endtime"],
                "hours": float(element["timebilled"]),
                "category": element["category"],
                "project": element["title"],
                "description": element["description"]
            }
            userReport.append(timebill)
        totalHours = float(data["data"][len(data["data"]) - 1]["timebilled"])
        userReport.append(totalHours)
        return userReport
    else:
        # print("Weekly: Incomplete hours or N/A")
        totalHours = 0
        userReport.append(totalHours)
        return userReport


# This function takes in the total hours worked in a single week (Mon-Friday), then does a check whether the total is
# >= 40 or < 40, then sends an email to the user.
def sendMail(totalHours, userId, startDate, endDate):
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(config('EMAIL_ADDRESS'), config('EMAIL_PASSWORD'))
    # server.sendmail(FROM, TO, MESSAGE)

    SUBJECT = "Subject: Weekly Timesheet Reminder: {startDate} - {endDate} \n\n".format(
        startDate=startDate, endDate=endDate)

    if totalHours >= 40:
        BODY = "Congratulations! You've worked %d hours this week." % (totalHours)
        message = SUBJECT + BODY
        print(message)
        server.sendmail("%s" % (config('EMAIL_ADDRESS')), "%s@connexservice.ca" % (userId), message)
    else:
        BODY = "You have completed %d hours this week. You have not completed sufficient hours this week. Please " \
               "update your hours on Q360" % (totalHours)
        message = SUBJECT + BODY
        print(message)
        server.sendmail("%s" % (config('EMAIL_ADDRESS')), "%s@connexservice.ca" % (userId), message)

    server.quit()


# **************************** APP ROUTING *****************************************
# **********************************************************************************

@app.route('/')
def home():
    return json.dumps(employeeHours)

@app.route('/table')
def table():
    return render_template("table.html")

#  ******************************* ALL USERID SEARCH *************************************
#  Get the total hours and time bills for all userIds (in CSV file) for the selected dates
#  ***************************************************************************************
@app.route('/getHoursForAllForCustom', methods=['GET'])
def getHoursForAllForCustom():
    #  Reads a csv file containing account credentials and calls the Q360 login function
    with open('accounts.csv', 'r') as csv_file:
        csv_reader = csv.reader(csv_file)

        next(csv_reader)  # Skip the first line in the csv file

        # Read each line in the csv file and call the login function: returnUserInfo(userId, password))
        for line in csv_reader:
            # Substitute "returnUserInfo" function with any date function, (ex. custom, month, week)
            returnUserInfoForCustom(line[0])
        # print("employeeHours:", employeeHours)
    return json.dumps(employeeHours)

@app.route('/getHoursForAllForWeek', methods=['GET'])
def getHoursForAllForWeek():
    #  Reads a csv file containing account credentials and calls the Q360 login function
    with open('accounts.csv', 'r') as csv_file:
        csv_reader = csv.reader(csv_file)

        next(csv_reader)  # Skip the first line in the csv file

        # Read each line in the csv file and call the login function: returnUserInfo(userId, password))
        for line in csv_reader:
            # Substitute "returnUserInfo" function with any date function, (ex. custom, month, week)
            returnUserInfoForWeek(line[0])
        # print("employeeHours:", employeeHours)
    return json.dumps(employeeHours)

@app.route('/getHoursForAllForMonth', methods=['GET'])
def getHoursForAllForMonth():
    #  Reads a csv file containing account credentials and calls the Q360 login function
    with open('accounts.csv', 'r') as csv_file:
        csv_reader = csv.reader(csv_file)

        next(csv_reader)  # Skip the first line in the csv file

        # Read each line in the csv file and call the login function: returnUserInfo(userId, password))
        for line in csv_reader:
            # Substitute "returnUserInfo" function with any date function, (ex. custom, month, week)
            returnUserInfoForMonth(line[0])
        # print("employeeHours:", employeeHours)
    return json.dumps(employeeHours)

#  ************************* SINGLE USERID SEARCH ********************************
#  Get the total hours and time bills for a specific userId for the selected dates
#  *******************************************************************************

@app.route('/getHoursForCustom', methods=['GET'])
def getHoursForCustom():
    # Example Endpoint Parameters: /getHoursForCustom?user=<userId>
    userId = request.args.get('user', default="", type=str)

    returnUserInfoForCustom(userId)  # Changeable date function
    return json.dumps(employeeHours[userId])

@app.route('/getHoursForWeek', methods=['GET'])
def getHoursForWeek():
    # Example Endpoint Parameters: /getHoursForWeek?user=<userId>
    userId = request.args.get('user', default="", type=str)

    returnUserInfoForWeek(userId)
    return json.dumps(employeeHours[userId])

@app.route('/getHoursForMonth', methods=['GET'])
def getHoursForMonth():
    # Example Endpoint Parameters: /getHoursForMonth?user=<userId>
    userId = request.args.get('user', default="", type=str)

    returnUserInfoForMonth(userId)
    return json.dumps(employeeHours[userId])


if __name__ == "__main__":
    app.run()
