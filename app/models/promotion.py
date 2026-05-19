from datetime import datetime
from app import db

class Promotion(db.Model):
    __tablename__ = 'promotions'
    
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    payment_status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Promotion {self.id} for Listing {self.listing_id}>'