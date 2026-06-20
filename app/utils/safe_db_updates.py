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

        # Business Account upgrade columns (ACCOUNT-BUSINESS-2026-06-20 spec, one-way)
        for col_name, col_type, col_default in [
            ('business_type', 'VARCHAR(80)', None),
            ('business_contact_person', 'VARCHAR(100)', None),
            ('business_phone', 'VARCHAR(30)', None),
            ('business_verified', 'BOOLEAN', '0'),
            ('upgraded_at', 'DATETIME', None),
        ]:
            if _column_exists(inspector, 'users', col_name):
                logger.info(f"Column '{col_name}' already exists on 'users' — skipping.")
            else:
                try:
                    default_sql = f" DEFAULT {col_default}" if col_default is not None else ""
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}{default_sql}"))
                    conn.commit()
                    logger.info(f"✅ Added '{col_name}' column to 'users' table (business upgrade).")
                except Exception as e:
                    logger.error(f"Failed to add {col_name} column: {e}")
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

        # raw_yoco_response on credit_transactions - store full Yoco response JSON for debugging when gateway data is inconsistent
        if _column_exists(inspector, 'credit_transactions', 'raw_yoco_response'):
            logger.info("Column 'raw_yoco_response' already exists on 'credit_transactions' — skipping.")
        else:
            try:
                conn.execute(text("ALTER TABLE credit_transactions ADD COLUMN raw_yoco_response TEXT"))
                conn.commit()
                logger.info("✅ Added 'raw_yoco_response' column to 'credit_transactions' table (full Yoco response for reliability).")
            except Exception as e:
                logger.error(f"Failed to add raw_yoco_response column to credit_transactions: {e}")
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

    # Unlimited Credit Passes table (PAYG-UNLIMITED-2026-06-20)
    try:
        create_user_credit_passes_table(db)
    except Exception as ex:
        logger.warning(f"Non-fatal error creating user_credit_passes table: {ex}")

    # Site-wide hit counter / views since launch
    try:
        create_site_stats_table(db)
    except Exception as ex:
        logger.warning(f"Non-fatal error creating site_stats table: {ex}")


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

        # Ensure the main 'payments' table has all columns used by the current model
        # (listing_id was added for promotions, yoco_* columns for Yoco checkout)
        payments_cols = [
            ('listing_id', "ALTER TABLE payments ADD COLUMN listing_id INTEGER NULL"),
            ('yoco_checkout_id', "ALTER TABLE payments ADD COLUMN yoco_checkout_id VARCHAR(100) NULL"),
            ('yoco_status', "ALTER TABLE payments ADD COLUMN yoco_status VARCHAR(50) NULL"),
            ('transaction_id', "ALTER TABLE payments ADD COLUMN transaction_id VARCHAR(100) NULL"),
            ('updated_at', "ALTER TABLE payments ADD COLUMN updated_at DATETIME NULL"),
            ('payment_method', "ALTER TABLE payments ADD COLUMN payment_method VARCHAR(50) DEFAULT 'yoco'"),
        ]
        for col_name, alter_sql in payments_cols:
            if _column_exists(inspector, 'payments', col_name):
                logger.info(f"Column '{col_name}' already exists on 'payments' — skipping.")
            else:
                try:
                    from sqlalchemy import text as sa_text
                    # Table might not exist yet on a completely fresh DB
                    conn.execute(sa_text(alter_sql))
                    conn.commit()
                    logger.info(f"✅ Added '{col_name}' column to 'payments' table.")
                except Exception as e:
                    # Table may not exist at all yet — safe to ignore (will be created on first use or via create_all)
                    logger.warning(f"Could not add {col_name} to payments (table may not exist yet): {e}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass

        # As a last resort for very old DBs, ensure a minimal payments table exists
        try:
            from sqlalchemy import text as sa_text
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    listing_id INTEGER NULL,
                    amount FLOAT NOT NULL,
                    currency VARCHAR(10) DEFAULT 'ZAR',
                    payment_method VARCHAR(50) DEFAULT 'yoco',
                    status VARCHAR(20) DEFAULT 'pending',
                    transaction_id VARCHAR(100),
                    yoco_checkout_id VARCHAR(100),
                    yoco_status VARCHAR(50),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(listing_id) REFERENCES listings(id)
                )
            """))
            conn.commit()
            logger.info("✅ Ensured base 'payments' table structure exists.")
        except Exception as e:
            logger.warning(f"payments table ensure note: {e}")

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


def create_user_credit_passes_table(db):
    """Create user_credit_passes table for Unlimited Credit Passes (one-time 30/60/90 day).
    Idempotent CREATE TABLE IF NOT EXISTS.
    """
    from sqlalchemy import text

    try:
        engine = db.engine
        inspector = inspect(engine)
    except Exception as ex:
        logger.warning(f"Could not obtain inspector for user_credit_passes: {ex}")
        return

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_credit_passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                pass_type VARCHAR(20) NOT NULL,
                duration_days INTEGER NOT NULL,
                starts_at DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                amount_paid DECIMAL(10,2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'ZAR',
                yoco_checkout_id VARCHAR(100) UNIQUE,
                payment_status VARCHAR(20) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """))
        conn.commit()
        logger.info("✅ Ensured user_credit_passes table exists (Unlimited Credit Passes).")


def create_site_stats_table(db):
    """Create site_stats table for global hit counter ("X views since launch").
    Idempotent. Uses the SiteStat model when possible.
    """
    from sqlalchemy import text

    try:
        engine = db.engine
        inspector = inspect(engine)
    except Exception as ex:
        logger.warning(f"Could not obtain inspector for site_stats: {ex}")
        return

    with engine.connect() as conn:
        # Create the table if it does not exist (works on fresh DBs)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS site_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(64) NOT NULL UNIQUE,
                value INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()
        logger.info("✅ Ensured site_stats table exists (for total site views counter).")

