"""
Safe one-time script to add new columns for Rental post type + Multiple Photos support.

Run this from the project root:
    python add_rental_photo_columns.py

It only adds the columns if they don't already exist.
Always backup your DB first!
"""

import os
import shutil
import sqlite3

DB_PATH = 'instance/volstruisgids.db'

NEW_COLUMNS = [
    ('rental_duration', 'INTEGER'),
    ('rental_duration_unit', 'VARCHAR(20)'),
    ('photo_urls', 'TEXT'),
]

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cursor.fetchall())

def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    print(f"📦 Backing up {DB_PATH} ...")
    backup_path = DB_PATH + '.backup'
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Backup created: {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    added = []
    for col_name, col_type in NEW_COLUMNS:
        if not column_exists(cursor, 'listings', col_name):
            try:
                cursor.execute(f"ALTER TABLE listings ADD COLUMN {col_name} {col_type}")
                added.append(col_name)
                print(f"➕ Added column: {col_name} ({col_type})")
            except Exception as e:
                print(f"⚠️  Failed to add {col_name}: {e}")
        else:
            print(f"✓ Column already exists: {col_name}")

    if added:
        conn.commit()
        print(f"\n✅ Successfully added {len(added)} new column(s): {', '.join(added)}")
    else:
        print("\n✅ No new columns were needed.")

    conn.close()
    print("\n🔄 Please restart your Flask application.")

if __name__ == "__main__":
    main()
