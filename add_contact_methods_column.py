"""
Safe, idempotent script to add the `contact_methods` column to the listings table.

This enables the new multi-select contact options (DM / Email / Phone) when posting listings.

Run this from the project root on BOTH dev and production:

    python add_contact_methods_column.py

Features:
- Creates a timestamped backup first (in instance/backups/ and next to DB).
- Only adds the column if it does not already exist (via PRAGMA check).
- Works for SQLite.
- Existing listings will have NULL (treated as 'dm,email,phone' for backward compatibility in templates/routes).

IMPORTANT:
- Run this after deploying code that includes the contact_methods changes (model + form + routes + templates).
- Restart the app after running.
- For production, take a manual backup first in addition to what this does.

You can delete this script after successful run on all environments.
"""

import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = 'instance/volstruisgids.db'
NEW_COLUMN = 'contact_methods'
NEW_COLUMN_TYPE = 'VARCHAR(100)'  # or TEXT


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cursor.fetchall())


def main():
    print("=" * 60)
    print("Volstruis Gids - Add contact_methods Column")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"❌ ERROR: Database not found at {DB_PATH}")
        print("   Run the app at least once to create the DB, then re-run this script.")
        return

    # Backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(os.path.dirname(DB_PATH) or '.', 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    backup_name = f"volstruisgids.db.backup_before_contact_methods_{timestamp}"
    backup_path = os.path.join(backup_dir, backup_name)
    print(f"\n📦 Backing up database...")
    shutil.copy2(DB_PATH, backup_path)
    print(f"✅ Backup saved to: {backup_path}")

    simple_backup = f"{DB_PATH}.backup_contact_{timestamp}"
    shutil.copy2(DB_PATH, simple_backup)
    print(f"✅ Also: {simple_backup}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if column_exists(cursor, 'listings', NEW_COLUMN):
        print(f"\n✓ Column '{NEW_COLUMN}' already exists in listings table. Nothing to do.")
    else:
        print(f"\n➕ Adding column '{NEW_COLUMN}' ({NEW_COLUMN_TYPE}) to listings table...")
        try:
            cursor.execute(f"ALTER TABLE listings ADD COLUMN {NEW_COLUMN} {NEW_COLUMN_TYPE}")
            conn.commit()
            print(f"✅ Successfully added '{NEW_COLUMN}' column.")
            print("   (Existing rows will have NULL, which the app treats as the default 'dm,email,phone'.)")
        except Exception as e:
            print(f"❌ Failed to add column: {e}")
            conn.rollback()
            conn.close()
            return

    # Verify
    cursor.execute("PRAGMA table_info(listings);")
    cols = [row[1] for row in cursor.fetchall()]
    print(f"\n📋 Current 'contact_*' columns in listings: {[c for c in cols if 'contact' in c]}")

    conn.close()

    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("  1. Restart your Flask app (dev or production).")
    print("  2. The contact selection on create/quick_create/edit will now be multi-checkbox (DM + Email + Phone).")
    print("  3. Detail pages will respect the seller's chosen contact methods (including DM button).")
    print("  4. (Optional) Delete this script.")
    print("=" * 60)


if __name__ == "__main__":
    main()
