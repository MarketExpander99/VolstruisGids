from datetime import datetime, timedelta
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
    # Multi-select contact methods: comma-separated e.g. 'dm,email,phone'
    # Supports DM (in-app private messaging), Email, Phone/WhatsApp
    contact_methods = db.Column(db.String(100), default='dm,email,phone')
    
    is_active = db.Column(db.Boolean, default=True)
    is_business_ad = db.Column(db.Boolean, default=False)
    is_promoted = db.Column(db.Boolean, default=False)  # Set on paid promotion purchase (or boost); badge shows only when True. Future: can derive/expire from Promotion records.
    views = db.Column(db.Integer, default=0)
    
    # === Credit System v1.0 additions (added only - no existing columns removed) ===
    listing_type = db.Column(db.String(20), default='normal')  # normal / super
    last_reposted_at = db.Column(db.DateTime, nullable=True)
    # v1.2 spec: refreshed_at for repost/refresh (falls back to last_reposted_at / created_at)
    refreshed_at = db.Column(db.DateTime, nullable=True)
    
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
        """Return human-readable price string for templates and API responses.
        Formatted with thousands separator and 2 decimals, e.g. R 1,234.00
        """
        def fmt(val):
            if val is None:
                return "0.00"
            try:
                return f"{float(val):,.2f}"
            except (ValueError, TypeError):
                return str(val)

        if self.post_type == 'rental' and self.price is not None:
            duration = self.rental_duration or 1
            unit = self.rental_duration_unit or 'day'
            unit_label = {'day': 'day', 'week': 'week', 'month': 'month'}.get(unit, 'day')
            return f"R {fmt(self.price)} per {unit_label} (min {duration} {unit_label}s)"
        if self.price_type == 'range' and self.min_price is not None and self.max_price is not None:
            return f"R {fmt(self.min_price)} – R {fmt(self.max_price)}"
        if self.price_type == 'negotiable':
            return "Negotiable"
        if self.price is not None:
            return f"R {fmt(self.price)}"
        if self.price_type == 'free':
            return "Free"
        return "Price on request"

    # ============================================================
    # Listing freshness / expiration (7-day public visibility rule)
    # No DB column added. Computed dynamically.
    # ============================================================

    @property
    def freshness_date(self):
        """Effective date for public freshness (respects boosts/reposts). v1.2 uses refreshed_at if present."""
        return self.refreshed_at or self.last_reposted_at or self.created_at

    @property
    def is_expired(self):
        """True if older than 7 days (based on freshness_date) and should be hidden from public homepage/search."""
        base = self.freshness_date
        if base is None:
            return False
        return (datetime.utcnow() - base).days > 7

    @property
    def days_old(self):
        """Integer days since original creation (for owner-facing messages)."""
        if self.created_at is None:
            return 0
        return (datetime.utcnow() - self.created_at).days

    @property
    def days_since_freshness(self):
        """Days since last posted or reposted (for 'expired N days ago' messaging)."""
        base = self.freshness_date
        if base is None:
            return 0
        return (datetime.utcnow() - base).days

    # ============================================================
    # v1.1 / v1.2 Spec aliases for "effective freshness"
    # effective_date respects refreshed_at (preferred), last_reposted_at, created_at
    # ============================================================
    @property
    def effective_date(self):
        """Effective date for freshness/7-day window (spec v1.2)."""
        return self.refreshed_at or self.last_reposted_at or self.created_at

    @property
    def is_active_listing(self):
        """True if this listing counts as an 'active' (non-expired) slot for free-tier rules."""
        return not self.is_expired