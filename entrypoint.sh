#!/bin/sh
set -e

DB_PATH="${DATABASE:-q360.db}"

if [ ! -f "$DB_PATH" ]; then
    flask --app run:app init-db
fi

exec gunicorn --bind 0.0.0.0:8080 run:app
