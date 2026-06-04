#!/usr/bin/env python
"""
Safe, non-destructive database schema sync.

Ensures all columns from the current Listing model exist (price range, rental, photos, boost/promoted, contact_methods, allow_comments, listing_type etc.).
Works for both:
  - Production: PostgreSQL (PythonAnywhere, etc.)
  - Local dev: SQLite

- Idempotent (safe to run multiple times)
- Uses "ADD COLUMN IF NOT EXISTS" + proper defaults
- Backfills existing rows where sensible
- Never drops data or tables

Run this after deploying code that added new columns to the model.
This fixes 500 errors on /api/listings and similar (caused by missing columns in the DB).
"""

import sys
from sqlalchemy import text
from app import create_app, db


def main():
    print("=== Volstruis Gids DB Schema Sync ===")
    print("This will safely add any missing columns from the current Listing model.")
    print("It is idempotent and will NOT delete or alter existing data.\n")

    app = create_app()
    with app.app_context():
        db_uri = str(db.engine.url)
        # Mask credentials in output
        safe_uri = db_uri.split('@')[-1] if '@' in db_uri else db_uri
        print(f"Connected to: {safe_uri}")

        is_postgres = 'postgresql' in db_uri.lower() or 'postgres' in db_uri.lower()
        is_sqlite = 'sqlite' in db_uri.lower()

        if is_postgres:
            print("✓ PostgreSQL detected. Proceeding with safe ALTERs...")
        elif is_sqlite:
            print("✓ SQLite detected (local dev). Script is non-destructive. Proceeding automatically...")
        else:
            print("\n⚠️  WARNING: Unrecognized database type.")
            answer = input("Continue anyway? (yes/no): ").strip().lower()
            if answer != "yes":
                print("Aborted by user.")
                return

        with db.engine.connect() as conn:
            trans = conn.begin()
            try:
                def ensure_column(table, column_def):
                    """Add column only if it doesn't exist. Handles SQLite vs Postgres differences."""
                    col_name = column_def.split()[0]
                    if is_postgres:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_def};"))
                        return True
                    else:
                        # SQLite: check first
                        res = conn.execute(text(f"PRAGMA table_info({table});"))
                        existing = [row[1] for row in res.fetchall()]
                        if col_name not in existing:
                            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def};"))
                            return True
                        return False

                # === Price range support ===
                if ensure_column('listings', "price_type VARCHAR(10) DEFAULT 'fixed' NOT NULL"):
                    print("✓ price_type column added (default 'fixed', NOT NULL)")
                else:
                    print("✓ price_type column already exists")

                if ensure_column('listings', "min_price FLOAT"):
                    print("✓ min_price column added")
                else:
                    print("✓ min_price column already exists")

                if ensure_column('listings', "max_price FLOAT"):
                    print("✓ max_price column added")
                else:
                    print("✓ max_price column already exists")

                result = conn.execute(text("""
                    UPDATE listings 
                    SET price_type = 'fixed' 
                    WHERE price_type IS NULL OR price_type = '';
                """))
                if result.rowcount > 0:
                    print(f"✓ Backfilled price_type='fixed' on {result.rowcount} existing rows")

                # === Rental + multi-photo support ===
                if ensure_column('listings', "rental_duration INTEGER"):
                    print("✓ rental_duration column added")
                else:
                    print("✓ rental_duration column already exists")

                if ensure_column('listings', "rental_duration_unit VARCHAR(20)"):
                    print("✓ rental_duration_unit column added")
                else:
                    print("✓ rental_duration_unit column already exists")

                if ensure_column('listings', "photo_urls TEXT"):
                    print("✓ photo_urls column added")
                else:
                    print("✓ photo_urls column already exists")

                # === Boost / promoted listings ===
                if ensure_column('listings', "is_promoted BOOLEAN DEFAULT FALSE"):
                    print("✓ is_promoted column added")
                else:
                    print("✓ is_promoted column already exists")

                if ensure_column('listings', "last_reposted_at TIMESTAMP"):
                    print("✓ last_reposted_at column added")
                else:
                    print("✓ last_reposted_at column already exists")

                result = conn.execute(text("""
                    UPDATE listings SET is_promoted = FALSE WHERE is_promoted IS NULL;
                """))
                if result.rowcount > 0:
                    print(f"✓ Backfilled is_promoted=FALSE on {result.rowcount} rows")

                # === Multi-select contact methods (DM/Email/Phone) ===
                if ensure_column('listings', "contact_methods VARCHAR(100) DEFAULT 'dm,email,phone'"):
                    print("✓ contact_methods column added")
                else:
                    print("✓ contact_methods column already exists")

                result = conn.execute(text("""
                    UPDATE listings 
                    SET contact_methods = 'dm,email,phone' 
                    WHERE contact_methods IS NULL OR contact_methods = '';
                """))
                if result.rowcount > 0:
                    print(f"✓ Backfilled contact_methods on {result.rowcount} rows")

                # === Other recent columns ===
                if ensure_column('listings', "allow_comments BOOLEAN DEFAULT TRUE"):
                    print("✓ allow_comments column added")
                else:
                    print("✓ allow_comments column already exists")

                if ensure_column('listings', "listing_type VARCHAR(20) DEFAULT 'normal'"):
                    print("✓ listing_type column added")
                else:
                    print("✓ listing_type column already exists")

                result = conn.execute(text("""
                    UPDATE listings SET allow_comments = TRUE WHERE allow_comments IS NULL;
                """))
                if result.rowcount > 0:
                    print(f"✓ Backfilled allow_comments on {result.rowcount} rows")

                trans.commit()
                print("\n✅ DB schema sync completed successfully!")
                print("   All Listing model columns now exist.")
                print("   /api/listings and homepage should now return valid JSON (no more 500s or JSON parse errors).")
                print("   Restart your app (Flask dev server or PythonAnywhere web app).")

            except Exception as e:
                trans.rollback()
                print(f"\n❌ Sync failed: {e}")
                print("   No changes were committed. Check the error and try again.")
                sys.exit(1)


if __name__ == "__main__":
    main()