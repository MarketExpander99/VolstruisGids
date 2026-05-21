from datetime import datetime
from app import db

class Listing(db.Model):
    __tablename__ = 'listings'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=True)
    location = db.Column(db.String(100), nullable=False, index=True)
    area = db.Column(db.String(100), nullable=False, index=True, server_default="")
    contact_phone = db.Column(db.String(20))
    contact_email = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True)
    is_business_ad = db.Column(db.Boolean, default=False)
    is_promoted = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    photo_url = db.Column(db.String(255))
    allow_comments = db.Column(db.Boolean, default=True, nullable=True)
    
    # Post Type
    post_type = db.Column(db.String(20), default='sale')   # sale, wanted, announcement
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    
    promotions = db.relationship('Promotion', backref='listing', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='listing', lazy='dynamic')
    
    # ✅ Fixed: relationship needed for business branding in feed
    user = db.relationship('User', backref='listings', lazy=True)
    
    def __repr__(self):
        return f'<Listing {self.title}>'