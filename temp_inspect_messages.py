import sqlite3
import os

DB_PATH = 'instance/volstruisgids.db'

print(f"Checking DB at: {DB_PATH}")
print(f"Exists: {os.path.exists(DB_PATH)}")

if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages';")
    exists = cursor.fetchone()
    print('messages table exists:', bool(exists))
    if exists:
        cursor.execute('PRAGMA table_info(messages);')
        cols = cursor.fetchall()
        print('Columns (cid, name, type, notnull, dflt_value, pk):')
        for c in cols:
            print('  ', c)

        cursor.execute("PRAGMA foreign_key_list(messages);")
        fks = cursor.fetchall()
        print('Foreign keys:')
        for fk in fks:
            print('  ', fk)
    else:
        print('Table does not exist yet - will be created by the update script.')
    conn.close()
else:
    print('DB file missing - script will handle gracefully (but you probably have one in prod).')
