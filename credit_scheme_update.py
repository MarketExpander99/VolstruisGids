#!/usr/bin/env python3
"""
Safe, non-destructive schema update for Credit-Based Monetization System v1.0
Adds columns to users and listings tables + creates credit_transactions table.
Uses raw SQL checks + db.create_all() so existing data is never lost.
Run this after updating the model files and app/__init__.py.
"""

import os
from sqlalchemy import text
from app import create_app, db


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a SQLite table using PRAGMA."""
    result = conn.execute(text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result.fetchall()]
    return column_name in columns


def main():
    app = create_app()
    with app.app_context():
        print("🔧 Starting safe credit schema update (v1.0)...")
        
        conn = db.engine.connect()
        
        # --- USERS table additions ---
        print("Checking users table...")
        if not column_exists(conn, 'users', 'account_type'):
            print("  → Adding account_type column...")
            conn.execute(text("ALTER TABLE users ADD COLUMN account_type VARCHAR(20) DEFAULT 'personal'"))
        else:
            print("  ✓ account_type already exists")
            
        if not column_exists(conn, 'users', 'credit_balance'):
            print("  → Adding credit_balance column...")
            conn.execute(text("ALTER TABLE users ADD COLUMN credit_balance INTEGER DEFAULT 0"))
        else:
            print("  ✓ credit_balance already exists")
        
        # --- LISTINGS table additions ---
        print("Checking listings table...")
        if not column_exists(conn, 'listings', 'listing_type'):
            print("  → Adding listing_type column...")
            conn.execute(text("ALTER TABLE listings ADD COLUMN listing_type VARCHAR(20) DEFAULT 'normal'"))
        else:
            print("  ✓ listing_type already exists")
            
        if not column_exists(conn, 'listings', 'last_reposted_at'):
            print("  → Adding last_reposted_at column...")
            conn.execute(text("ALTER TABLE listings ADD COLUMN last_reposted_at DATETIME"))
        else:
            print("  ✓ last_reposted_at already exists")
        
        conn.close()
        
        # Create new credit_transactions table (safe - does nothing if exists)
        print("Ensuring credit_transactions table exists...")
        db.create_all()
        
        print("\n✅ Credit schema update completed successfully!")
        print("   - All new columns added (or already present)")
        print("   - credit_transactions table ready")
        print("   - Zero data loss. All existing listings/users preserved.")
        print("\nNext steps:")
        print("  1. Restart your Flask dev server")
        print("  2. Test by registering a new user and checking credit_balance == 0")
        print("  3. (Optional) python -c \"from app import create_app, db; app=create_app(); print('DB OK')\"")


if __name__ == '__main__':
    main()