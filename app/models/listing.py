from datetime import datetime
from app import db

class Listing(db.Model):
    __tablename__ = 'listings'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(100), nullable=False, index=True)
    contact_phone = db.Column(db.String(20))
    contact_email = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True)
    is_promoted = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    
    # Relationships
    promotions = db.relationship('Promotion', backref='listing', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='listing', lazy='dynamic')
    
    def __repr__(self):
        return f'<Listing {self.title}>'