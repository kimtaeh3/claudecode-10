FROM tiangolo/uwsgi-nginx-flask:python3.8

ENV UWSGI_INI /app/uwsgi.app.ini

COPY . /app
WORKDIR /app

RUN pip3 install -r requirements.txt