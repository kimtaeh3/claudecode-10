"""One-time script: import accounts.csv into team_member table."""
import csv, sqlite3, sys

db_path = sys.argv[1] if len(sys.argv) > 1 else 'q360.db'
csv_path = sys.argv[2] if len(sys.argv) > 2 else 'accounts.csv'

conn = sqlite3.connect(db_path)
with open(csv_path) as f:
    reader = csv.reader(f)
    next(reader)
    rows = [(row[0].strip(), row[1].strip()) for row in reader if row]
conn.executemany('INSERT OR IGNORE INTO team_member (username, team) VALUES (?,?)', rows)
conn.commit()
conn.close()
print(f'Imported {len(rows)} members from {csv_path}')
