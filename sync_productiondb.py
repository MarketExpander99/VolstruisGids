#!/usr/bin/env python
"""
Safe, non-destructive database schema sync for production (PostgreSQL on PythonAnywhere).

Adds the missing price-range columns (price_type, min_price, max_price) to the listings table.
- Idempotent (safe to run multiple times)
- Uses IF NOT EXISTS + proper defaults
- Backfills existing rows
- Never drops data or tables
- Respects DATABASE_URL (or falls back to SQLite for dev)

Run this ONLY ONCE on production after you have deployed the latest code.
"""

import sys
from sqlalchemy import text
from app import create_app, db


def main():
    print("=== VolstruisGids Production DB Sync ===")
    print("This will safely add price range columns if missing.")
    print("It is idempotent and will NOT delete or alter existing data.\n")

    app = create_app()
    with app.app_context():
        db_uri = str(db.engine.url)
        # Mask credentials in output
        safe_uri = db_uri.split('@')[-1] if '@' in db_uri else db_uri
        print(f"Connected to: {safe_uri}")

        if 'postgresql' not in db_uri.lower() and 'postgres' not in db_uri.lower():
            print("\n⚠️  WARNING: This does not appear to be a PostgreSQL connection.")
            print("   For local SQLite dev you should use fix_database.py instead (destructive).")
            answer = input("Continue anyway on this database? (yes/no): ").strip().lower()
            if answer != "yes":
                print("Aborted by user.")
                return

        with db.engine.connect() as conn:
            trans = conn.begin()
            try:
                # price_type: matches model (String 10, default 'fixed', NOT NULL)
                conn.execute(text("""
                    ALTER TABLE listings 
                    ADD COLUMN IF NOT EXISTS price_type VARCHAR(10) DEFAULT 'fixed' NOT NULL;
                """))
                print("✓ price_type column ensured (default 'fixed', NOT NULL)")

                # min_price: nullable Float
                conn.execute(text("""
                    ALTER TABLE listings 
                    ADD COLUMN IF NOT EXISTS min_price FLOAT;
                """))
                print("✓ min_price column ensured")

                # max_price: nullable Float
                conn.execute(text("""
                    ALTER TABLE listings 
                    ADD COLUMN IF NOT EXISTS max_price FLOAT;
                """))
                print("✓ max_price column ensured")

                # Safety backfill for any pre-existing rows
                result = conn.execute(text("""
                    UPDATE listings 
                    SET price_type = 'fixed' 
                    WHERE price_type IS NULL OR price_type = '';
                """))
                if result.rowcount > 0:
                    print(f"✓ Backfilled price_type='fixed' on {result.rowcount} existing rows")

                trans.commit()
                print("\n✅ Production DB sync completed successfully!")
                print("   Range-price listings can now be saved without column errors.")
                print("   Index and detail pages will display ranges correctly.")
                print("   You can now reload the web app on PythonAnywhere.")

            except Exception as e:
                trans.rollback()
                print(f"\n❌ Sync failed: {e}")
                print("   No changes were committed. Check the error and try again.")
                sys.exit(1)


if __name__ == "__main__":
    main()