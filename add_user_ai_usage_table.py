"""
Safe one-time script to create the user_ai_usage table
(for daily free Grok chat quota tracking + rate limit signals).

Run this from the project root:
    python add_user_ai_usage_table.py

It uses CREATE TABLE IF NOT EXISTS so it is safe to re-run.
Always backup your DB first (the script does a quick copy).

This is required because the table was introduced in the
"Free Grok AI Integration + Unlimited Photo Uploads" change
and the live SQLite DB may not have it yet.
"""

import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = 'instance/volstruisgids.db'


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        print("   Start the app at least once (python run.py) so it creates the instance/ folder + base tables.")
        return

    print(f"📦 Backing up {DB_PATH} ...")
    backup_path = f"{DB_PATH}.backup_before_ai_usage_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ Backup created: {backup_path}")
    except Exception as e:
        print(f"⚠️  Could not backup (continuing anyway): {e}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Idempotent create (matches the model + safe_db_updates)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_ai_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                usage_date DATE NOT NULL,
                free_chat_used INTEGER NOT NULL DEFAULT 0,
                total_ai_calls INTEGER NOT NULL DEFAULT 0,
                last_ai_call_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id),
                UNIQUE(user_id, usage_date)
            )
        """)

        # Best-effort indexes
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_user_ai_usage_user_id ON user_ai_usage (user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_user_ai_usage_usage_date ON user_ai_usage (usage_date)")
        except Exception:
            pass

        conn.commit()
        print("✅ user_ai_usage table ensured (created if missing).")

        # Quick sanity
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_ai_usage';")
        if cursor.fetchone():
            print("✅ Table 'user_ai_usage' is now present.")
        else:
            print("⚠️  Table creation may have been skipped (check permissions).")

    except Exception as e:
        print(f"❌ Error creating table: {e}")
        conn.rollback()
    finally:
        conn.close()

    print("\nDone. Now restart your dev server (the app will also auto-create it via safe_db_updates on next start).")


if __name__ == "__main__":
    main()
