from datetime import datetime
from app import db


class Listing(db.Model):
    __tablename__ = 'listings'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    
    # Pricing - nullable=True in model (for range/negotiable), but some legacy DBs may still have NOT NULL.
    # Creation code sets price=0.0 for range as safe placeholder; display logic prefers price_type + min/max.
    price = db.Column(db.Float, nullable=True)                    # kept for legacy fixed price
    price_type = db.Column(db.String(10), default='fixed', nullable=False)  # 'fixed' or 'range'
    min_price = db.Column(db.Float, nullable=True)
    max_price = db.Column(db.Float, nullable=True)
    
    # Rental specific (when post_type == 'rental')
    rental_duration = db.Column(db.Integer, nullable=True)
    rental_duration_unit = db.Column(db.String(20), nullable=True)  # 'day', 'week', 'month'
    
    location = db.Column(db.String(100), nullable=False, index=True)
    area = db.Column(db.String(100), nullable=False, index=True, server_default="")
    contact_phone = db.Column(db.String(20))
    contact_email = db.Column(db.String(120))
    
    is_active = db.Column(db.Boolean, default=True)
    is_business_ad = db.Column(db.Boolean, default=False)
    is_promoted = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    
    # === Credit System v1.0 additions (added only - no existing columns removed) ===
    listing_type = db.Column(db.String(20), default='normal')  # normal / super
    last_reposted_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    photo_url = db.Column(db.String(255))
    photo_urls = db.Column(db.Text)  # comma-separated list of additional photo URLs (first is in photo_url)
    allow_comments = db.Column(db.Boolean, default=True, nullable=True)
    
    # Post Type
    post_type = db.Column(db.String(20), default='sale')   # sale, wanted, announcement, services, rental
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    
    # Relationships (preserved exactly)
    promotions = db.relationship('Promotion', backref='listing', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='listing', lazy='dynamic')
    
    # Fixed: relationship needed for business branding in feed
    user = db.relationship('User', backref='listings', lazy=True)
    
    def __repr__(self):
        return f'<Listing {self.title}>'
    
    def get_display_price(self):
        """Return human-readable price string for templates and API responses."""
        if self.post_type == 'rental' and self.price is not None:
            duration = self.rental_duration or 1
            unit = self.rental_duration_unit or 'day'
            unit_label = {'day': 'day', 'week': 'week', 'month': 'month'}.get(unit, 'day')
            return f"R{int(self.price)} per {unit_label} (min {duration} {unit_label}s)"
        if self.price_type == 'range' and self.min_price is not None and self.max_price is not None:
            return f"R{int(self.min_price)} - R{int(self.max_price)}"
        if self.price_type == 'negotiable':
            return "Negotiable"
        if self.price is not None:
            return f"R{int(self.price)}"
        if self.price_type == 'free':
            return "Free"
        return "Price on request"