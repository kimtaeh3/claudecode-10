import requests
from flask import Flask, request, render_template
from flask_ngrok import run_with_ngrok

import json

app = Flask(__name__)
run_with_ngrok(app)

from Login360 import Login360


# @app.route('/userlookup/<userid>')
# def userlookup(userid):
#     test = Login360();
#     json_data = json.loads(test.returnUserInfo(userid))
#     for x in json_data['data']:
#         print(x['timebilled'])
#     return str(test.returnUserInfo(userid))

@app.route('/')
def home():
   return render_template('index.html')

@app.route('/user', methods=['GET'])
def user():
    # Example Endpoint Parameters: /user?userId=username&pass=password
    userId = request.args.get('userId', default="", type=str)
    password = request.args.get('pass', default='*', type=str)

    test = Login360()
    return str(test.returnUserInfo(userId, password))
    # return "Your username is %s and password is %s" % (userId, password)




# @app.route('/', methods=['GET'])
# def index():
#     test = Login360();
#     return render_template('index.html');
    # return "Welcome to the Q360 Automation Tool"
    # return (test.returnResponse())
    # return str(test.returnResponse())
    # return str(test.returnUserInfo())


if __name__ == "__main__":
    app.run()
