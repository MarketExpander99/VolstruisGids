"""
CreditTransaction model for VolstruisGids
Tracks all credit movements (daily free grants, purchases, boosts, etc.)
Klein Karoo community classifieds platform
"""

from app import db
from datetime import datetime
from decimal import Decimal


class CreditTransaction(db.Model):
    __tablename__ = 'credit_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False, index=True)  # 'daily_free', 'purchase', 'boost_listing', 'share_reward', etc.
    reference = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=True)  # pending / success (for Yoco credit purchases)
    raw_yoco_response = db.Column(db.Text, nullable=True)  # full Yoco response (JSON string) for reliability/debugging when Yoco data varies
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Optional backref if you want easy access from User later
    # user = db.relationship('User', backref=db.backref('credit_transactions', lazy='dynamic'))

    def __repr__(self):
        return f'<CreditTransaction user_id={self.user_id} type={self.transaction_type} amount={self.amount}>'