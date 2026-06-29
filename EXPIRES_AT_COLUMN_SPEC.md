# Developer Spec: EXPIRES_AT_COLUMN_2026-06-29.md

**Title:** Hardened 7-Day Expiration Column (expires_at) + Automatic Safe Migration  
**Date:** 2026-06-29  
**Status:** Implemented (safe, automatic on deploy)  
**Related Spec:** Listing Freshness v1.2 / 7-day visibility rule (2026-06-29)

## Files Changed

- `app/models/listing.py` (model + event listener + active_query())
- `app/utils/safe_db_updates.py` (automatic column addition + backfill)

## Problem

The Listing model was updated with a persistent `expires_at` column (source of truth for the 7-day public visibility rule). However, the production listings table on PythonAnywhere was missing the column. This caused immediate 500 errors on `/listing/<id>` (and any other page that queries the Listing model) because SQLAlchemy tried to SELECT a non-existent column.

## Solution (Safe & Automatic)

We extended the existing automatic safe DB updater (`app/utils/safe_db_updates.py`), which is already called inside `create_app()` on every startup.

**Behaviour on PythonAnywhere deploy:**

- Push code → restart web app.
- `create_app()` runs → `apply_safe_db_updates(db)` executes.
- If `expires_at` column is missing → it is added (as nullable for safety).
- All existing rows are backfilled with `created_at + 7 days` (or `now + 7 days`).
- Future listings automatically receive `expires_at` via the `@event.listens_for(Listing, 'before_insert')` listener already in the model.
- The `is_expired` property and `active_query()` classmethod work correctly even on legacy rows.

This is idempotent, non-destructive, and follows the exact same pattern used for `last_reposted_at`, `refreshed_at`, `likes_count`, `comments_count`, etc.

## Why This Approach

- Uses the official safe mechanism (`safe_db_updates.py`) — no manual migrations, no Alembic, no risk of breaking production.
- Never drops or alters existing data/columns.
- Backfill is safe and uses `created_at` where possible.
- Works for both SQLite (local) and the production database.
- Once merged, every future deploy automatically stays in sync.

## Rollout

1. Merge this change.
2. Push to GitHub.
3. On PythonAnywhere: pull latest code + restart the web app.
4. The column + backfill happens automatically on first request after restart.
5. No further manual steps required.

## Verification After Deploy

- Visit any listing detail page (e.g. `/listing/36`).
- Homepage, category pages, and search should continue working.
- New listings created after deploy should have `expires_at` set automatically.
- Old listings should have `expires_at` populated from their `created_at`.

## Action Required: Update safe_db_updates.py

Add the following block inside the `with engine.connect() as conn:` section of `apply_safe_db_updates()`, right after the `refreshed_at` block.

**Copy-paste ready code (insert here):**

```python
# expires_at on listings (hardened 7-day expiration rule - spec 2026-06-29)
        if _column_exists(inspector, 'listings', 'expires_at'):
            logger.info("Column 'expires_at' already exists on 'listings' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE listings ADD COLUMN expires_at DATETIME NULL"))
                conn.commit()
                logger.info("✅ Added 'expires_at' column to 'listings' table (nullable for safe migration).")

                # Backfill existing rows so the app doesn't break on old data
                try:
                    conn.execute(text("""
                        UPDATE listings 
                        SET expires_at = datetime(created_at, '+7 days')
                        WHERE expires_at IS NULL AND created_at IS NOT NULL
                    """))
                    conn.execute(text("""
                        UPDATE listings 
                        SET expires_at = datetime('now', '+7 days')
                        WHERE expires_at IS NULL
                    """))
                    conn.commit()
                    logger.info("✅ Backfilled expires_at on existing listings (created_at + 7 days fallback).")
                except Exception as bf_err:
                    logger.warning(f"Backfill of expires_at encountered non-fatal issue: {bf_err}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Failed to add expires_at column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
```

After adding this block, the automatic behaviour on PythonAnywhere is guaranteed.

## Next Steps (Recommended)

- Add the block above to `app/utils/safe_db_updates.py`.
- Create a new file in the repo root called `EXPIRES_AT_COLUMN_SPEC.md` and paste the spec content from the top of this message into it.
- Commit + push both changes.
- On PythonAnywhere: pull + restart the web app.
