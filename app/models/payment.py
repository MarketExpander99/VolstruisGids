from datetime import datetime
from app import db

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=True)  # for promotions
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='ZAR')
    payment_method = db.Column(db.String(50), default='yoco')  # 'yoco' or 'credits'
    status = db.Column(db.String(20), default='pending')  # pending, success, failed, refunded
    transaction_id = db.Column(db.String(100), unique=True)
    
    # === Yoco specific fields (added for Yoco Checkout pivot) ===
    yoco_checkout_id = db.Column(db.String(100), unique=True, nullable=True)
    yoco_status = db.Column(db.String(50), nullable=True)  # created, paid, cancelled, etc.
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Payment {self.id} - {self.status} - {self.amount} {self.currency}>'