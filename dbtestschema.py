import sqlite3

connection = sqlite3.connect('q360test_db.db')
cursor = connection.cursor()

cursor.execute("DROP TABLE if EXISTS user")
cursor.execute("DROP TABLE if EXISTS project")
cursor.execute("DROP TABLE if EXISTS project_assignment")
cursor.execute("DROP TABLE if EXISTS forecast")
cursor.execute("DROP TABLE if EXISTS forecast_week")

user_db_create = """CREATE TABLE IF NOT EXISTS user (
  user_id SERIAL PRIMARY KEY NOT NULL, 
  username VARCHAR(50) NOT NULL,
  full_name VARCHAR(50) NOT NULL,
  title VARCHAR(50) NOT NULL,
  is_a_team_lead BOOLEAN NOT NULL DEFAULT FALSE,
  reports_to INTEGER REFERENCES user(user_id)
  )"""

project_db_create = """CREATE TABLE IF NOT EXISTS project (
  project_id SERIAL PRIMARY KEY NOT NULL, 
  project_number INTEGER NOT NULL,
  project_task_number INTEGER NOT NULL,
  project_name VARCHAR(50) NOT NULL,
  company VARCHAR(50) NOT NULL,
  progress VARCHAR(50) NOT NULL,
  utilization VARCHAR(50) NOT NULL,
  project_manager INTEGER REFERENCES user(user_id) ON DELETE CASCADE
  )"""

project_assignment_db_create = """CREATE TABLE IF NOT EXISTS project_assignment (
  project_assignment_id SERIAL PRIMARY KEY NOT NULL, 
  project_id INTEGER REFERENCES project(project_id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES user(user_id) ON DELETE CASCADE,
  project_hours FLOAT(2) NOT NULL
  )"""

forecast_db_create = """CREATE TABLE IF NOT EXISTS forecast (
  forecast_id SERIAL PRIMARY KEY NOT NULL, 
  progress VARCHAR(50) NOT NULL,
  task_id INTEGER,
  customer VARCHAR(50) NOT NULL,
  sow VARCHAR(50) NOT NULL,
  utilization VARCHAR(50) NOT NULL,
  project_name VARCHAR(50) REFERENCES project(project_name) ON DELETE CASCADE,
  team VARCHAR(50) NOT NULL,
  pm INTEGER REFERENCES user(user_id) ON DELETE CASCADE,
  team_lead INTEGER REFERENCES user(user_id) ON DELETE CASCADE,
  sub_org VARCHAR(50) NOT NULL,
  cost VARCHAR(50) NOT NULL,
  resources INTEGER REFERENCES user(user_id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL,
  hrs_rate VARCHAR(50),
  perc VARCHAR(50),
  alloc INTEGER,
  con FLOAT(2) NOT NULL,
  forecast INTEGER NOT NULL,
  rem INTEGER NOT NULL
  )"""

forecast_week_db_create = """CREATE TABLE IF NOT EXISTS forecast_week (
  forecast_week_id SERIAL PRIMARY KEY NOT NULL, 
  task_id INTEGER REFERENCES forecast(forecast_id) ON DELETE CASCADE,
  week VARCHAR(50),
  custom VARCHAR(50),
  hr INTEGER
  )"""

cursor.execute(user_db_create)
cursor.execute(project_db_create)
cursor.execute(project_assignment_db_create)
cursor.execute(forecast_db_create)
cursor.execute(forecast_week_db_create)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cursor.fetchall())