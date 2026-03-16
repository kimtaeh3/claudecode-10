import psycopg2
from decouple import config
import psycopg2.extras

hostname = config('DB_HOSTNAME')
database = config('DB_DATABASE')
username = config('DB_USERNAME')
pwd = config('DB_PWD')
port_id = config('DB_PORT_ID')

conn = None

try: 
    with psycopg2.connect(
                host = hostname,
                dbname = database, 
                user = username,
                password = pwd,
                port = port_id
    ) as conn: 

        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

            cur.execute('DROP TABLE IF EXISTS users CASCADE')
            cur.execute('DROP TABLE IF EXISTS projects CASCADE')
            cur.execute('DROP TABLE IF EXISTS forecasts CASCADE')
            cur.execute('DROP TABLE IF EXISTS project_assignments CASCADE')

            #Creating Table for Users
            create_script = ''' CREATE TABLE IF NOT EXISTS users (
                                     id      serial NOT NULL PRIMARY KEY,
                                     userID  varchar NOT NULL,
                                     first_name  varchar,
                                     last_name varchar,
                                     team_lead varchar(50) DEFAULT NULL,
                                     role varchar(50) DEFAULT NULL) '''
            cur.execute(create_script)

            # insert_script  = 'INSERT INTO users (userID, first_name, last_name, team_lead, role) VALUES (%s, %s, %s, %s, %s)'
            # insert_values = ('u1', 'James', 'Porter', 'Faadhil', 'Dev')

            # cur.execute(insert_script, insert_values)


            create_script = ''' CREATE TABLE IF NOT EXISTS projects (
                                     id      serial NOT NULL PRIMARY KEY,
                                     project_name  varchar(100),
                                     total_hours  float,
                                     forecast_id int DEFAULT NULL) '''
            cur.execute(create_script)


            create_script = ''' CREATE TABLE IF NOT EXISTS forecasts (
                                     id      serial NOT NULL PRIMARY KEY,
                                     date  DATE,
                                     total_hours  float) '''
            cur.execute(create_script)


            create_script = ''' CREATE TABLE IF NOT EXISTS project_assignments (
                                     id      serial NOT NULL PRIMARY KEY,
                                     user_id int DEFAULT NULL REFERENCES users (id),
                                     project_id int DEFAULT NULL REFERENCES projects (id)) '''
            cur.execute(create_script)

            # cur.execute('DROP TABLE IF EXISTS employee')

            # create_script = ''' CREATE TABLE IF NOT EXISTS employee (
            #                         id      int PRIMARY KEY,
            #                         name    varchar(40) NOT NULL,
            #                         salary  int,
            #                         dept_id varchar(30)) '''
            # cur.execute(create_script)

            # insert_script  = 'INSERT INTO employee (id, name, salary, dept_id) VALUES (%s, %s, %s, %s)'
            # insert_values = [(1, 'James', 12000, 'D1'), (2, 'Robin', 15000, 'D1'), (3, 'Xavier', 20000, 'D2')]
            # for record in insert_values:
            #     cur.execute(insert_script, record)

            # update_script = 'UPDATE employee SET salary = salary + (salary * 0.5)'
            # cur.execute(update_script)

            # delete_script = 'DELETE FROM employee WHERE name = %s'
            # delete_record = ('James',)
            # cur.execute(delete_script, delete_record)

            # cur.execute('SELECT * FROM EMPLOYEE')
            # for record in cur.fetchall():
            #     print(record['name'], record['salary'])

except Exception as error:
    print(error)

finally:
    if conn is not None:
        conn.close()