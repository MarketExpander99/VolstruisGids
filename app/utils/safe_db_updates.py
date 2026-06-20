"""
VolstruisGids Safe Database Update Script (Credit System v1.2)
Idempotent. Checks existence before changing structure.
Runs automatically on app startup from create_app().

Adds (if missing):
- users.credit_balance (NUMERIC for 0.5 credit increments / Share-to-Earn)
- users.subscription_type
- users.last_share_reward_date, users.shares_rewarded_today (for daily share cap)
- listings.last_reposted_at
- listings.refreshed_at (per v1.2 spec for repost freshness)
- Also supports legacy 'credits' column name for spec alignment

Safe to run repeatedly. Uses SQLAlchemy inspector.
Works for SQLite (primary) and other DBs.
"""

from sqlalchemy import text, inspect
import logging

logger = logging.getLogger(__name__)


def apply_safe_db_updates(db):
    """Run safe structural updates. Call from create_app() after db.init_app(app)."""
    try:
        engine = db.engine
        inspector = inspect(engine)
    except Exception as ex:
        logger.warning(f"Could not obtain engine/inspector for safe updates: {ex}")
        return

    with engine.connect() as conn:
        # 1. credit_balance on users (use NUMERIC(10,2) to support 0.5 rewards)
        if _column_exists(inspector, 'users', 'credit_balance'):
            logger.info("Column 'credit_balance' already exists on 'users' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN credit_balance NUMERIC(10,2) NULL DEFAULT 0"))
                conn.commit()
                logger.info("✅ Added 'credit_balance' column (Numeric) to 'users' table.")
            except Exception as e:
                logger.error(f"Failed to add credit_balance column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        # credits column (direct spec name support, Numeric for 0.5)
        if _column_exists(inspector, 'users', 'credits'):
            logger.info("Column 'credits' already exists on 'users' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN credits NUMERIC(10,2) NULL DEFAULT 0"))
                conn.commit()
                logger.info("✅ Added 'credits' column (Numeric) to 'users' table.")
            except Exception as e:
                logger.error(f"Failed to add credits column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        # subscription_type
        if _column_exists(inspector, 'users', 'subscription_type'):
            logger.info("Column 'subscription_type' already exists on 'users' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN subscription_type VARCHAR(20) DEFAULT 'free'"))
                conn.commit()
                logger.info("✅ Added 'subscription_type' column to 'users' table.")
            except Exception as e:
                logger.error(f"Failed to add subscription_type column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        # last_share_reward_date (DATE for Share-to-Earn daily tracking)
        if _column_exists(inspector, 'users', 'last_share_reward_date'):
            logger.info("Column 'last_share_reward_date' already exists on 'users' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_share_reward_date DATE NULL"))
                conn.commit()
                logger.info("✅ Added 'last_share_reward_date' column to 'users' table.")
            except Exception as e:
                logger.error(f"Failed to add last_share_reward_date column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        # shares_rewarded_today (INT, reset daily)
        if _column_exists(inspector, 'users', 'shares_rewarded_today'):
            logger.info("Column 'shares_rewarded_today' already exists on 'users' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN shares_rewarded_today INTEGER DEFAULT 0"))
                conn.commit()
                logger.info("✅ Added 'shares_rewarded_today' column to 'users' table.")
            except Exception as e:
                logger.error(f"Failed to add shares_rewarded_today column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        # last_reposted_at on listings
        if _column_exists(inspector, 'listings', 'last_reposted_at'):
            logger.info("Column 'last_reposted_at' already exists on 'listings' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE listings ADD COLUMN last_reposted_at DATETIME NULL"))
                conn.commit()
                logger.info("✅ Added 'last_reposted_at' column to 'listings' table.")
            except Exception as e:
                logger.error(f"Failed to add last_reposted_at column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        # refreshed_at on listings (v1.2 spec column for effective freshness)
        if _column_exists(inspector, 'listings', 'refreshed_at'):
            logger.info("Column 'refreshed_at' already exists on 'listings' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE listings ADD COLUMN refreshed_at DATETIME NULL"))
                conn.commit()
                logger.info("✅ Added 'refreshed_at' column to 'listings' table.")
            except Exception as e:
                logger.error(f"Failed to add refreshed_at column: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

        # status on credit_transactions (required for Yoco _fulfill_credit_purchase idempotency in prod)
        if _column_exists(inspector, 'credit_transactions', 'status'):
            logger.info("Column 'status' already exists on 'credit_transactions' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE credit_transactions ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"))
                conn.commit()
                logger.info("✅ Added 'status' column to 'credit_transactions' table (for payment fulfillment).")
            except Exception as e:
                logger.error(f"Failed to add status column to credit_transactions: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

    logger.info("Safe DB update check completed.")

    # Call payment tables creation (Stripe credit packs + subscriptions)
    try:
        create_payment_tables(db)
    except Exception as ex:
        logger.warning(f"Non-fatal error creating payment tables: {ex}")


def create_payment_tables(db):
    """Create payment_transactions table (idempotent) + ensure Stripe user columns.
    Per spec v1 for Credit Top-up and Monthly Business Subscriptions.
    """
    from sqlalchemy import text

    try:
        engine = db.engine
        inspector = inspect(engine)
    except Exception as ex:
        logger.warning(f"Could not obtain inspector for payment tables: {ex}")
        return

    with engine.connect() as conn:
        # Create payment_transactions table if it doesn't exist
        # FK references the actual table name 'users'
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payment_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                credits_added DECIMAL(10,2) NOT NULL,
                stripe_session_id VARCHAR(255),
                stripe_payment_intent VARCHAR(255),
                status VARCHAR(50) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """))
        conn.commit()
        logger.info("✅ Ensured payment_transactions table exists.")

        # Ensure stripe user columns exist (safe adds)
        stripe_user_cols = [
            ('stripe_customer_id', "ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255) NULL"),
            ('stripe_subscription_id', "ALTER TABLE users ADD COLUMN stripe_subscription_id VARCHAR(255) NULL"),
            ('subscription_status', "ALTER TABLE users ADD COLUMN subscription_status VARCHAR(50) DEFAULT 'none'"),
            ('subscription_current_period_end', "ALTER TABLE users ADD COLUMN subscription_current_period_end DATETIME NULL"),
        ]
        for col_name, alter_sql in stripe_user_cols:
            if _column_exists(inspector, 'users', col_name):
                logger.info(f"Column '{col_name}' already exists on 'users' — skipping.")
            else:
                try:
                    conn.execute(text(alter_sql))
                    conn.commit()
                    logger.info(f"✅ Added '{col_name}' column to 'users' table.")
                except Exception as e:
                    logger.error(f"Failed to add {col_name} column: {e}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass

    logger.info("✅ Payment tables + Stripe columns ensured.")


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    try:
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        # Table may not exist yet (first run); safe to return False so create_all later will handle basics
        return False
