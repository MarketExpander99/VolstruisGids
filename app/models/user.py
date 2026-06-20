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

    def __repr__(self):
        return f'<User {self.username}>'