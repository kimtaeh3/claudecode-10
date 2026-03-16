import requests
import json
import smtplib
from decouple import config
from datetime import datetime, timedelta


class Login360:

    def returnUserInfo(self, userId, password):
        lastDayofWeek = datetime.date(datetime.now())  # Friday
        firstDayofWeek = lastDayofWeek - timedelta(days=4)  # Monday

        url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action%3Dlogin'
        cookies = dict(cookies_are='working')

        header = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                  'X-Requested-With': 'XMLHttpRequest',
                  'Referer': 'https://websupport.connexservice.ca/controller.php?action=login'}
        url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action=login'

        files = {'jsonRequest': '{"userid": "%s","password": "%s","touch":"false"}' % (userId, password)}

        s = requests.Session()
        r2 = s.get('https://websupport.connexservice.ca/controller.php?action=login', cookies=cookies, verify=False);
        r = s.post(url, headers=header, data=files, cookies=cookies, verify=False)

        url2 = 'https://websupport.connexservice.ca/ajax/'
        files2 = {"userid": "sabala", "startdate": "2021-12-06", "enddate": "2021-12-17",
                  "_a": "get_timebill_byuseriddetail"}
        # files2 = {"userid": userId, "startdate": firstDayofWeek, "enddate": lastDayofWeek,
        #           "_a": "get_timebill_byuseriddetail"}
        r = s.post(url2, headers=header, data=files2, cookies=cookies, verify=False)

        url = 'https://websupport.connexservice.ca/ajax/?_a=authenticate&_r=action%3Dlogin%27'

        print()
        print(r.text)
        print("firstDayofWeek:", firstDayofWeek)
        print("lastDayofWeek:", lastDayofWeek)
        weeklyTimebillTotal = parseJson(r.text)  # Converts employee timesheet text to JSON
        # sendMail(weeklyTimebillTotal, userId, firstDayofWeek, lastDayofWeek)
        return r.text


# This function parses the text from the API to JSON
def parseJson(jsonString):
    data = json.loads(jsonString)
    print(data["data"][len(data["data"]) - 1]["timebilled"])
    weeklyTimebillTotal = float(data["data"][len(data["data"]) - 1]["timebilled"])
    return weeklyTimebillTotal


# This function takes in the total hours worked in a single week (Mon-Friday), then does a check whether the total is
# >= 40 or < 40, then sends an email to the user.
def sendMail(weeklyTimebillTotal, userId, firstDayofWeek, lastDayofWeek):
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(config('EMAIL_ADDRESS'), config('EMAIL_PASSWORD'))
    # server.sendmail(FROM, TO, MESSAGE)

    SUBJECT = "Subject: Weekly Timesheet Reminder: {firstDayofWeek} - {lastDayofWeek} \n\n".format(
        firstDayofWeek=firstDayofWeek, lastDayofWeek=lastDayofWeek)

    if weeklyTimebillTotal >= 40:
        BODY = "Congratulations! You've worked %d hours this week." % (weeklyTimebillTotal)
        message = SUBJECT + BODY
        print(message)
        # server.sendmail("%s" % (config('EMAIL_ADDRESS')), "%s@connexservice.ca" % (userId), message)
    else:
        BODY = "You have completed %d hours this week. You have not completed sufficient hours this week. Please " \
               "update your hours on Q360" % (weeklyTimebillTotal)
        message = SUBJECT + BODY
        print(message)
        # server.sendmail("%s" % (config('EMAIL_ADDRESS')), "%s@connexservice.ca" % (userId), message)

    server.quit()
