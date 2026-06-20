"""
UserCreditPass model — one-time Unlimited Credit Passes (30/60/90 days).
Pay once for unlimited promotions (no credit deductions) for the duration.
"""

from app import db
from datetime import datetime


class UserCreditPass(db.Model):
    __tablename__ = 'user_credit_passes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    pass_type = db.Column(db.String(20), nullable=False)  # '30_day', '60_day', '90_day'
    duration_days = db.Column(db.Integer, nullable=False)

    starts_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    amount_paid = db.Column(db.Numeric(10, 2), nullable=False)  # e.g. 299.00
    currency = db.Column(db.String(10), default='ZAR')

    yoco_checkout_id = db.Column(db.String(100), unique=True, nullable=True)
    payment_status = db.Column(db.String(20), default='pending')  # pending / success

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<UserCreditPass user={self.user_id} type={self.pass_type} expires={self.expires_at}>'
