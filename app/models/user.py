from datetime import datetime, date
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

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
    credit_balance = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # ============================================================
    # Daily Free Credit Refresh (+2 credits once per day)
    # ============================================================
    def ensure_daily_free_credits(self):
        """Give the user +2 free credits once per day if they haven't received them today."""
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

        self.credit_balance += 2

        tx = CreditTransaction(
            user_id=self.id,
            amount=2,
            transaction_type='daily_free',
            reference=f'daily_free_{today.isoformat()}'
        )
        db.session.add(tx)
        db.session.commit()
        return True

    def __repr__(self):
        return f'<User {self.username}>'