Q360 Automation Tool

Checks employee hours for the week and sends an email reminder if the total weekly hours is below 40.
UI to send time bill hours more efficiently.

### Setup

1) Create a python virtual environment:  <br>
https://docs.python.org/3/library/venv.html  <br>
https://www.infoworld.com/article/3239675/virtualenv-and-venv-python-virtual-environments-explained.html#:~:text=To%20use%20the%20virtual%20environment,just%20run%20python%20myscript.py%20.


2) Install the following dependencies for Python:

  i) Activate virtualenv ($source path_to_virtualenv/bin/activate)

  ii) Go to your project root directory

  iii) Get all the packages along with dependencies in requirements.txt
    ```
    pip freeze > requirements.txt
    ```
    
  iv) Install packages from requirements.txt
    ```
    pip install -r requirements.txt
    ```

3) Create a .env file and paste the following code. Add credential values:
```
# Q360 Email Credentials:
EMAIL_ADDRESS=
EMAIL_PASSWORD=
```

4) Database:
Current ERD can be found here https://app.diagrams.net/#G1XN5SVNzZdP35kGBxnwomYq1HRa9vrTD8
In the root folder run the re-schema and re-seed files:
    ```
    python dbtestschema.py
    ```
    ```
    python dbtestseed.py
    ```
  This will create the SQLite3 database file - q360test_db.db

5) Visual Browser for Database:
Please download DB Browser for SQLite
```
https://sqlitebrowser.org/dl/
```
In the DB Browser:
File -> Open Database -> Select the q360test_db.db file
Browse Data tab allows for viewing the tables and Execute SQL allows for queries against the DB

6) Branching Strategies:
Commit to Feature Branch > Merge to Dev Brench > Merge to QA Branch > Merge to Main Branch
