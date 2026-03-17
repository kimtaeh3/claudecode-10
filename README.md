Q360 Automation Tool

Web app for automating Q360 hour submission. Supports single and bulk Excel uploads for multiple employees.

### Features

- **Submit Hours** — submit hours for any user with a Confirm → Submit two-step flow
- **Bulk Upload** — parse `.xlsx`/`.xlsb` Excel files, review entries per employee/week, and submit in bulk
  - Auto-derives username from Employee name when Username column is missing
  - Skips days where existing + new hours would exceed 8h; allows submission when total ≤ 8h
  - Filter entries by type (guessed, needs attention, missing week, < 40h)
- **Hours View** — view logged hours by user or team across a date range
- **Forecast** — weekly hours forecast view

### Setup

#### Local Development

1. Create a Python virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Initialize the database:
   ```
   flask --app run:app init-db
   ```

4. Run the app:
   ```
   flask --app run:app run
   ```

#### Docker / Production

The app is containerized and deployed via Docker Compose. On startup, `entrypoint.sh` automatically runs `init-db` before launching gunicorn.

```
docker compose up -d
```

The container image is built and pushed to GitHub Container Registry (ghcr.io) via GitHub Actions on every push to `main`.

### Environment

No `.env` file is required for basic operation. The app authenticates against the Q360 API using credentials entered at login.

### Database

SQLite database stored at `/app/data/q360.db` (Docker volume) or `./data/q360.db` locally. Schema is in `app/schema.sql` and initialized automatically on startup.
