#!/bin/sh
set -e

flask --app run:app init-db

exec gunicorn --bind 0.0.0.0:8080 run:app
