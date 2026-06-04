"""
Safe, idempotent script to ensure the `messages` table exists for the Private Messaging (DM) MVP.

This table is required for the new in-app messaging system between users (linked to listings).

Run this from the project root on BOTH dev and production:

    python add_messages_table.py

Features:
- Always creates a timestamped backup before any changes.
- Uses CREATE TABLE IF NOT EXISTS (safe to run multiple times).
- If the table already exists, it will verify all required columns and add any that are missing (via ALTER TABLE).
- Includes foreign key constraints matching the SQLAlchemy model.
- Works with the project's SQLite setup (instance/volstruisgids.db).

IMPORTANT:
- Run this BEFORE starting the app after pulling the latest code that includes the messages feature.
- For production: take an extra manual backup of your live DB first.
- After running, restart your Flask app / WSGI server.
- This is a standalone script (no Flask app context required).

You can safely delete this file after running it on all environments.
"""

import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = 'instance/volstruisgids.db'

# Full table definition matching app/models/message.py
CREATE_MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    listing_id INTEGER,
    text TEXT NOT NULL,
    read BOOLEAN DEFAULT 0,
    timestamp DATETIME,
    FOREIGN KEY(sender_id) REFERENCES users(id),
    FOREIGN KEY(receiver_id) REFERENCES users(id),
    FOREIGN KEY(listing_id) REFERENCES listings(id)
);
"""

# Expected columns (name, type) for verification / ALTER on existing tables
EXPECTED_COLUMNS = [
    ('id', 'INTEGER'),
    ('sender_id', 'INTEGER'),
    ('receiver_id', 'INTEGER'),
    ('listing_id', 'INTEGER'),
    ('text', 'TEXT'),
    ('read', 'BOOLEAN'),
    ('timestamp', 'DATETIME'),
]


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
        (table_name,)
    )
    return cursor.fetchone() is not None


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cursor.fetchall())


def main():
    print("=" * 60)
    print("Volstruis Gids - Messages Table Setup Script")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"❌ ERROR: Database not found at {DB_PATH}")
        print("   Make sure you are running this from the project root,")
        print("   and that the database file has been created (run the app at least once).")
        return

    # === ALWAYS BACKUP ===
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(os.path.dirname(DB_PATH) or '.', 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    backup_filename = f"volstruisgids.db.backup_before_messages_{timestamp}"
    backup_path = os.path.join(backup_dir, backup_filename)

    print(f"\n📦 Creating backup...")
    print(f"   Source: {DB_PATH}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Backup created: {backup_path}")

    # Also keep a simple .backup in the instance folder for convenience (like previous scripts)
    simple_backup = DB_PATH + f'.backup_messages_{timestamp}'
    shutil.copy2(DB_PATH, simple_backup)
    print(f"✅ Simple backup also at: {simple_backup}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Enable foreign keys for this connection (good practice)
    cursor.execute("PRAGMA foreign_keys = ON;")

    changes_made = False

    if not table_exists(cursor, 'messages'):
        print("\n➕ messages table does not exist. Creating it now...")
        try:
            cursor.executescript(CREATE_MESSAGES_TABLE_SQL)
            conn.commit()
            changes_made = True
            print("✅ Successfully created 'messages' table with all columns and foreign keys.")
        except Exception as e:
            print(f"❌ Failed to create table: {e}")
            conn.rollback()
            conn.close()
            return
    else:
        print("\n✓ 'messages' table already exists. Checking for missing columns...")

        added_columns = []
        for col_name, col_type in EXPECTED_COLUMNS:
            if not column_exists(cursor, 'messages', col_name):
                try:
                    # Note: SQLite does not allow adding columns with constraints easily in all cases,
                    # but our columns are simple (the NOT NULL ones should already be there if table was partially created).
                    alter_sql = f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}"
                    cursor.execute(alter_sql)
                    added_columns.append(col_name)
                    print(f"   ➕ Added missing column: {col_name} ({col_type})")
                    changes_made = True
                except Exception as e:
                    print(f"   ⚠️  Could not add column {col_name}: {e}")
            else:
                print(f"   ✓ Column already present: {col_name}")

        if added_columns:
            conn.commit()
        else:
            print("   No columns were missing.")

    # Final verification
    cursor.execute("PRAGMA table_info(messages);")
    final_cols = [row[1] for row in cursor.fetchall()]
    print(f"\n📋 Final columns in 'messages' table: {final_cols}")

    cursor.execute("PRAGMA foreign_key_list(messages);")
    fks = cursor.fetchall()
    if fks:
        print(f"🔗 Foreign keys defined: {len(fks)} (sender_id, receiver_id, listing_id)")

    conn.close()

    if changes_made:
        print("\n✅ Database update complete!")
    else:
        print("\n✅ Database was already up to date. No changes needed.")

    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("  1. Restart your Flask application (dev or prod).")
    print("  2. The Messages link in the nav should now be active.")
    print("  3. Test by sending a private message from a listing detail page.")
    print("  4. (Optional) You can now delete this script if desired.")
    print("=" * 60)


if __name__ == "__main__":
    main()
