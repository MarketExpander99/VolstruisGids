"""
PaymentTransaction model for Stripe (and future provider) payments.
Records one-time credit pack purchases and subscription events.
Per Credit Top-up & Monthly Business Subscriptions spec v1.
"""

from app import db
from datetime import datetime
from decimal import Decimal


class PaymentTransaction(db.Model):
    __tablename__ = 'payment_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    credits_added = db.Column(db.Numeric(10, 2), nullable=False)
    stripe_session_id = db.Column(db.String(255))
    stripe_payment_intent = db.Column(db.String(255))
    status = db.Column(db.String(50), default='pending')  # pending, succeeded, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='payment_transactions')

    def __repr__(self):
        return f'<PaymentTransaction user_id={self.user_id} amount={self.amount} credits={self.credits_added} status={self.status}>'
