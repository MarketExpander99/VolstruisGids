from datetime import datetime, date
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal
import logging


logger = logging.getLogger(__name__)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    is_business = db.Column(db.Boolean, default=False)
    business_name = db.Column(db.String(100), nullable=True)
    business_type = db.Column(db.String(80), nullable=True)
    business_contact_person = db.Column(db.String(100), nullable=True)
    business_phone = db.Column(db.String(30), nullable=True)
    business_verified = db.Column(db.Boolean, default=False)
    upgraded_at = db.Column(db.DateTime, nullable=True)
    profile_pic = db.Column(db.String(200), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    posts_today = db.Column(db.Integer, default=0)

    account_type = db.Column(db.String(20), default='personal')
    credit_balance = db.Column(db.Numeric(10, 2), nullable=True, default=0)
    # Spec v1.2: direct credits column (Numeric supports 0.5 increments from Share-to-Earn)
    credits = db.Column(db.Numeric(10, 2), nullable=True, default=0)
    subscription_type = db.Column(db.String(20), default='free')  # free / personal / business_monthly (v1.1 scaffolding)

    # Stripe Billing fields (Credit Top-up + Monthly Business Subscriptions spec v1)
    stripe_customer_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)
    subscription_status = db.Column(db.String(50), default='none')  # none, active, past_due, canceled
    subscription_current_period_end = db.Column(db.DateTime, nullable=True)

    # Share-to-Earn daily tracking (v1.2)
    last_share_reward_date = db.Column(db.Date, nullable=True)
    shares_rewarded_today = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def credits(self):
        """Spec v1.2: Prefer dedicated credits col (Numeric) when populated, else fall back to credit_balance.
        Supports Decimal for 0.5 credit rewards. Setter supported for spec-style usage e.g. user.credits -= Decimal('1')
        """
        # Avoid recursion: access via __dict__ for the 'credits' column attr
        direct = self.__dict__.get('credits')
        if direct is not None:
            return direct
        return self.credit_balance or Decimal('0')

    @credits.setter
    def credits(self, value):
        # Store in both for maximum compat (credit_balance primary for legacy code, credits for spec)
        dec_val = value if isinstance(value, Decimal) else Decimal(str(value or 0))
        self.credit_balance = dec_val
        self.__dict__['credits'] = dec_val   # direct for col

    @property
    def is_business_account(self):
        """Canonical way to check if user is a business account.
        Uses both legacy is_business flag and account_type for robustness."""
        return bool(getattr(self, 'is_business', False) or getattr(self, 'account_type', None) == 'business')

    @property
    def storefront_enabled(self):
        """Business accounts only get the professional storefront experience."""
        return self.is_business_account

    @classmethod
    def get_by_username(cls, username):
        """Case-insensitive lookup for store / profile routes (VGD-SPEC-2026-06-23-001).
        Returns User or None. Uses safe lower() comparison to avoid LIKE wildcard surprises
        with usernames containing _ or %. Falls back gracefully.
        """
        if not username:
            return None
        uname = str(username).strip().lstrip('@')
        if not uname:
            return None
        try:
            from sqlalchemy import func
            # Safe exact case-insensitive match (no wildcard interpretation)
            u = cls.query.filter(func.lower(cls.username) == func.lower(uname)).first()
            if u:
                return u
        except Exception:
            pass
        try:
            # Fallback (original behaviour)
            return cls.query.filter(cls.username.ilike(uname)).first()
        except Exception:
            return None

    def set_credits(self, value):
        dec_val = value if isinstance(value, Decimal) else Decimal(str(value or 0))
        self.credit_balance = dec_val
        try:
            self.__dict__['credits'] = dec_val
        except Exception:
            pass

    # ============================================================
    # Daily Free Credit Refresh (+2 credits once per day)
    # Fully defensive production version - will never break login or run.py
    # ============================================================
    def ensure_daily_free_credits(self):
        """Give the user +2 free credits once per day if they haven't received them today."""
        try:
            today = date.today()
            start_of_day = datetime.combine(today, datetime.min.time())

            from app.models.credit_transaction import CreditTransaction

            already_received = CreditTransaction.query.filter(
                CreditTransaction.user_id == self.id,
                CreditTransaction.transaction_type == 'daily_free',
                CreditTransaction.created_at >= start_of_day
            ).first()

            if already_received:
                return False

            self.credit_balance = (self.credit_balance or Decimal('0')) + Decimal('2')

            tx = CreditTransaction(
                user_id=self.id,
                amount=Decimal('2'),
                transaction_type='daily_free',
                reference=f'daily_free_{today.isoformat()}'
            )
            db.session.add(tx)
            db.session.commit()
            return True

        except Exception as exc:
            db.session.rollback()
            logger.exception(
                f"Non-fatal error in ensure_daily_free_credits for user_id="
                f"{getattr(self, 'id', 'unknown')}: {exc}"
            )
            return False

    def has_active_unlimited_pass(self) -> bool:
        """Returns True if the user currently has an active unlimited credit pass.
        Credits are NEVER deducted while this returns True.
        """
        from app.models.user_credit_pass import UserCreditPass
        from datetime import datetime

        now = datetime.utcnow()
        return UserCreditPass.query.filter(
            UserCreditPass.user_id == self.id,
            UserCreditPass.starts_at <= now,
            UserCreditPass.expires_at >= now
        ).first() is not None

    # ============================================================
    # AI Free Quota + Rate Limit helpers (Free Grok AI spec 2026-06-20)
    # ============================================================
    @staticmethod
    def get_sast_today():
        """Return the calendar date in Africa/Johannesburg for daily reset at midnight SAST."""
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo('Africa/Johannesburg')
            return datetime.now(tz).date()
        except Exception:
            # Fallback: naive approx (server likely SAST anyway in prod)
            return datetime.utcnow().date()

    def get_ai_usage(self):
        """Get or create today's UserAIUsage row (SAST date).
        Defensive: will try to ensure the table exists if a query fails (first-run safety).
        """
        from app.models.user_ai_usage import UserAIUsage
        from app import db as _db
        today = self.get_sast_today()

        try:
            usage = UserAIUsage.query.filter_by(user_id=self.id, usage_date=today).first()
        except Exception:
            # Table probably missing on a dev DB that didn't run the safe update or script yet.
            self._ensure_ai_usage_table()
            usage = UserAIUsage.query.filter_by(user_id=self.id, usage_date=today).first()

        if not usage:
            usage = UserAIUsage(user_id=self.id, usage_date=today, free_chat_used=0, total_ai_calls=0)
            _db.session.add(usage)
            _db.session.commit()
        return usage

    def _ensure_ai_usage_table(self):
        """Last-resort: ensure the table exists using raw SQL (SQLite)."""
        from sqlalchemy import text
        try:
            from app import db as _db
            with _db.engine.connect() as conn:
                conn.execute(text("""
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
                """))
                conn.commit()
        except Exception:
            try:
                from app import db as _db
                _db.session.rollback()
            except Exception:
                pass

    def get_remaining_free_chat(self):
        """Return how many free chat questions remain today (max 2)."""
        if self.has_active_unlimited_pass():
            return 99
        usage = self.get_ai_usage()
        return max(0, 2 - (usage.free_chat_used or 0))

    def record_ai_chat_use(self, used_free=True):
        """Record one chat use. Increments free_chat_used if using free slot."""
        from app import db as _db
        from datetime import datetime
        usage = self.get_ai_usage()
        usage.free_chat_used = (usage.free_chat_used or 0) + (1 if used_free else 0)
        usage.total_ai_calls = (usage.total_ai_calls or 0) + 1
        usage.last_ai_call_at = datetime.utcnow()
        _db.session.commit()

    def check_ai_rate_limit(self, action='polish', max_per_hour=8):
        """Simple DB-backed hourly rate limit based primarily on CreditTransaction history.
        (UserAIUsage is used only for daily free_chat quota, not for hourly counting.)
        Returns (allowed: bool, message or None).
        """
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)

        # Primary source: CreditTransaction records (always present, we log every AI call with ai_* types)
        from app.models.credit_transaction import CreditTransaction
        tx_recent = CreditTransaction.query.filter(
            CreditTransaction.user_id == self.id,
            CreditTransaction.transaction_type.in_(['ai_improve', 'ai_improve_free', 'ai_query', 'ai_polish']),
            CreditTransaction.created_at >= one_hour_ago
        ).count()

        # Optional secondary (defensive): if UserAIUsage row exists and has recent last_ai_call_at, count it
        recent = 0
        try:
            from app.models.user_ai_usage import UserAIUsage
            recent = UserAIUsage.query.filter(
                UserAIUsage.user_id == self.id,
                UserAIUsage.last_ai_call_at >= one_hour_ago
            ).count()
        except Exception:
            # Table may not exist yet or other transient error — fall back to tx count only
            recent = 0

        total_recent = tx_recent + recent
        if total_recent >= max_per_hour:
            return False, f'Rate limit: max {max_per_hour} AI requests per hour. Please wait a bit.'
        return True, None

    def record_ai_action(self):
        """Update last call timestamp for rate limiting."""
        from app import db as _db
        from datetime import datetime
        usage = self.get_ai_usage()
        usage.last_ai_call_at = datetime.utcnow()
        usage.total_ai_calls = (usage.total_ai_calls or 0) + 1
        _db.session.commit()

    def sync_share_reward_counter(self):
        """Recompute shares_rewarded_today + last_share_reward_date from actual tx log.
        Safe to call often. Makes the denorm fields match reality (used for display).
        The cap enforcement itself now uses the tx count directly.
        """
        from app import db as _db
        from app.models.credit_transaction import CreditTransaction
        from datetime import datetime as dt

        try:
            sast_today = self.get_sast_today()
            start = dt.combine(sast_today, dt.min.time())

            count = CreditTransaction.query.filter(
                CreditTransaction.user_id == self.id,
                CreditTransaction.transaction_type == 'share_reward',
                CreditTransaction.created_at >= start
            ).count()

            changed = False
            if self.shares_rewarded_today != count:
                self.shares_rewarded_today = count
                changed = True
            if self.last_share_reward_date != sast_today:
                self.last_share_reward_date = sast_today
                changed = True

            if changed:
                _db.session.commit()
            return count
        except Exception:
            _db.session.rollback()
            return self.shares_rewarded_today or 0

    def __repr__(self):
        return f'<User {self.username}>'