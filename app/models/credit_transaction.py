from datetime import datetime
from app import db


class CreditTransaction(db.Model):
    __tablename__ = 'credit_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)           # positive = purchase, negative = spend
    transaction_type = db.Column(db.String(30), nullable=False)  # purchase, listing, repost, refund, free_quota
    reference = db.Column(db.String(100))    # Yoco transaction id or internal ref
    status = db.Column(db.String(20), default='pending')  # pending, success, failed, refunded
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship for easy querying (user.credit_transactions)
    user = db.relationship('User', backref=db.backref('credit_transactions', lazy='dynamic'))

    def __repr__(self):
        return f'<CreditTransaction {self.id} {self.transaction_type} {self.amount}>'