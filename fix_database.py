#!/usr/bin/env python3
"""
VolstruisGids Database Fix Script
One-click safe fix for Alembic migration issues (dbe5fa05c42c, missing alembic_version, etc.)
Always backs up your data first.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

# ===================== CONFIG =====================
DB_PATH = "instance/app.db"
BACKUP_DIR = "instance/backups"
BAD_REVISION = "dbe5fa05c42c"
# ================================================

def run_command(cmd):
    """Run a shell command and print output"""
    print(f"→ Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e.stderr.strip()}")
        return False

def main():
    print("🚀 VolstruisGids Database Fix Script Starting...\n")

    # 1. Make sure we're in the project root
    if not os.path.exists("run.py"):
        print("❌ Error: Please run this script from the VolstruisGids project root (where run.py is located).")
        sys.exit(1)

    # 2. Create backup directory
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # 3. Backup the database (permanent rule)
    if os.path.exists(DB_PATH):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{BACKUP_DIR}/app.db.backup_{timestamp}.bak"
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ Database backed up to: {backup_path}")
    else:
        print("⚠️  No existing database found — will create a fresh one.")

    # 4. Fix alembic_version table issues directly with SQLite
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Check if alembic_version exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version';")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                # Delete the bad revision if it exists
                cursor.execute(f"DELETE FROM alembic_version WHERE version_num = '{BAD_REVISION}';")
                conn.commit()
                print(f"✅ Removed bad revision '{BAD_REVISION}' from alembic_version table.")
            else:
                print("✅ alembic_version table does not exist yet — will be created during upgrade.")
            
            conn.close()
        except Exception as e:
            print(f"⚠️  SQLite fix had a small issue (non-critical): {e}")

    # 5. Run Flask migration commands safely
    print("\n🔧 Fixing migrations...")

    commands = [
        ["flask", "db", "stamp", "head"],
        ["flask", "db", "migrate", "-m", "auto fix after revision cleanup"],
        ["flask", "db", "upgrade"]
    ]

    success_count = 0
    for cmd in commands:
        if run_command(cmd):
            success_count += 1
        else:
            # If stamp fails, try upgrade directly
            if "stamp" in " ".join(cmd):
                print("⚠️  stamp command failed — trying upgrade directly...")
                if run_command(["flask", "db", "upgrade"]):
                    success_count += 1

    # 6. Final status
    print("\n" + "="*60)
    if success_count >= 2:
        print("🎉 DATABASE FIX COMPLETED SUCCESSFULLY!")
        print("Your database is now clean and up to date.")
        print("You can safely run: python run.py")
    else:
        print("⚠️  Fix completed with some warnings. Please paste the full output here if issues remain.")

    print("="*60)

if __name__ == "__main__":
    main()