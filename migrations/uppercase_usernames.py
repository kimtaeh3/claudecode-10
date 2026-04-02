"""
Migration: uppercase all usernames in db.
Run once: python migrations/uppercase_usernames.py
"""
import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'q360.db')

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # team_member: username must remain unique, so do it carefully
    members = cur.execute('SELECT id, username FROM team_member').fetchall()
    for row in members:
        up = row['username'].upper()
        if up != row['username']:
            # Check if the uppercase version already exists as a different row
            clash = cur.execute(
                'SELECT id FROM team_member WHERE username = ? AND id != ?', (up, row['id'])
            ).fetchone()
            if clash:
                print(f"  WARNING: cannot uppercase '{row['username']}' → '{up}': clash with id={clash['id']}")
            else:
                cur.execute('UPDATE team_member SET username = ? WHERE id = ?', (up, row['id']))
                print(f"  team_member id={row['id']}: '{row['username']}' → '{up}'")

    # bulk_hours
    cur.execute("UPDATE bulk_hours SET username = UPPER(username) WHERE username != UPPER(username)")
    print(f"  bulk_hours: {cur.rowcount} rows updated")

    # login_log
    cur.execute("UPDATE login_log SET username = UPPER(username) WHERE username != UPPER(username)")
    print(f"  login_log: {cur.rowcount} rows updated")

    # username_map (q360_username column)
    cur.execute("UPDATE username_map SET q360_username = UPPER(q360_username) WHERE q360_username != UPPER(q360_username)")
    print(f"  username_map.q360_username: {cur.rowcount} rows updated")

    # saved_filter: username column (owner) and usernames column (comma-separated list)
    filters = cur.execute('SELECT id, username, usernames FROM saved_filter').fetchall()
    for row in filters:
        new_owner = row['username'].upper() if row['username'] else row['username']
        new_list = ','.join(u.strip().upper() for u in row['usernames'].split(',')) if row['usernames'] else row['usernames']
        if new_owner != row['username'] or new_list != row['usernames']:
            cur.execute('UPDATE saved_filter SET username = ?, usernames = ? WHERE id = ?',
                        (new_owner, new_list, row['id']))
    print(f"  saved_filter: {cur.rowcount} rows updated")

    # user_project_pref
    cur.execute("UPDATE user_project_pref SET username = UPPER(username) WHERE username != UPPER(username)")
    print(f"  user_project_pref: {cur.rowcount} rows updated")

    conn.commit()
    conn.close()
    print("Done.")

if __name__ == '__main__':
    print(f"Migrating {os.path.abspath(DB_PATH)} ...")
    run()
