FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN flask --app run:app init-db

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "run:app"]
