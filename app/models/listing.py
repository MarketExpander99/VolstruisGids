from datetime import datetime, timedelta
from app import db
from sqlalchemy import event


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

    # Multi-town servicing (VGS-002): JSON array of towns selected by seller.
    # Legacy single-town listings continue to use `location`.
    # No cap on number of towns. 'Klein Karoo' is special region sentinel for full coverage.
    towns = db.Column(db.JSON, nullable=True, default=list)
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

    # 7-day automatic expiration (hardened per spec 2026-06-29)
    # Set to created_at + 7 days on creation; refreshed on repost/boost.
    # Indexed + composite (is_active, expires_at) for public query performance.
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    photo_url = db.Column(db.String(255))
    photo_urls = db.Column(db.Text)  # comma-separated list of additional photo URLs (first is in photo_url)
    allow_comments = db.Column(db.Boolean, default=True, nullable=True)
    
    # Community engagement denormalized counters (VolstruisGids spec 2026-06-25)
    likes_count = db.Column(db.Integer, default=0, nullable=False)
    comments_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Post Type
    post_type = db.Column(db.String(20), default='sale')   # sale, wanted, announcement, services, rental
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    
    # Relationships (preserved exactly)
    promotions = db.relationship('Promotion', backref='listing', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='listing', lazy='dynamic')
    
    # Fixed: relationship needed for business branding in feed
    user = db.relationship('User', backref='listings', lazy=True)
    
    # Social: likes & comments (spec: only on detail page; denorm counters)
    likes = db.relationship('Like', back_populates='listing', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', back_populates='listing', lazy='dynamic', order_by='Comment.created_at.desc()', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Listing {self.title}>'

    # ============================================================
    # Multi-town support (VGS-002)
    # ============================================================
    TOWNS = [
        'Calitzdorp',
        'Cape Town',
        'De Rust',
        'Dysselsdorp',
        'George',
        'Groenfontein',
        'Ladismith',
        'Mossel Bay',
        'Oudtshoorn',
        'Van Wyksdorp',
        'Zoar'
    ]
    KLEIN_KAROO = 'Klein Karoo'

    @property
    def town_list(self):
        """Return list of towns this listing covers.
        - Uses new `towns` JSON if populated.
        - Falls back to legacy single `location` for backward compat.
        - Always returns a list (never None/empty string).
        """
        if self.towns:
            try:
                if isinstance(self.towns, (list, tuple)):
                    cleaned = [str(t).strip() for t in self.towns if t and str(t).strip()]
                    if cleaned:
                        return cleaned
                elif isinstance(self.towns, str):
                    # In case stored as plain string somehow
                    t = self.towns.strip()
                    if t:
                        return [t]
            except Exception:
                pass
        if self.location:
            loc = str(self.location).strip()
            if loc:
                return [loc]
        return []

    def covers_town(self, town: str) -> bool:
        """True if this listing serves the given town (for filtering)."""
        if not town:
            return True
        tl = self.town_list
        if town in tl:
            return True
        # Klein Karoo provides full region coverage
        if self.KLEIN_KAROO in tl:
            return True
        return False

    def get_town_display(self):
        """Human friendly display: comma list, or 'Klein Karoo' special."""
        tl = self.town_list
        if not tl:
            return 'Klein Karoo'
        if self.KLEIN_KAROO in tl:
            # If ONLY Klein Karoo or mixed, prefer showing region when selected
            if len(tl) == 1 or tl == [self.KLEIN_KAROO]:
                return self.KLEIN_KAROO
            # mixed: show specific + region note? keep as list but note full
            others = [t for t in tl if t != self.KLEIN_KAROO]
            if others:
                return ', '.join(others) + f' + {self.KLEIN_KAROO}'
            return self.KLEIN_KAROO
        return ', '.join(tl)
    
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
    # Hardened: expires_at is the single source of truth for public visibility.
    # Old computed props preserved for UI (my_listings, profile cards) compatibility.
    # ============================================================

    @classmethod
    def active_query(cls):
        """Single source of truth for all public listing retrieval.
        Returns only listings that are:
          - is_active=True (not sold/deactivated)
          - not yet past their expires_at
        All homepage, category, search, API feeds, storefronts etc. must use this.
        """
        return cls.query.filter(
            cls.is_active == True,
            cls.expires_at > datetime.utcnow()
        )

    @property
    def freshness_date(self):
        """Effective date for public freshness (respects boosts/reposts)."""
        return self.refreshed_at or self.last_reposted_at or self.created_at

    @property
    def is_expired(self):
        """Authoritative expiry check.
        Prefers the persistent expires_at column (new hardened rule).
        Falls back to dynamic calculation only if expires_at missing (pre-migration rows).
        """
        if getattr(self, 'expires_at', None) is not None:
            return self.expires_at <= datetime.utcnow()
        # Legacy fallback (should be rare after migration + backfill)
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

    # ============================================================
    # Community engagement (spec 2026-06-25)
    # Denormalized counts to avoid COUNT(*) on every render.
    # Call after any Like or Comment mutation.
    # ============================================================
    def update_counts(self):
        """Recalculate and persist likes_count and comments_count."""
        from app.models.like import Like
        from app.models.comment import Comment
        try:
            self.likes_count = Like.query.filter_by(listing_id=self.id).count()
            self.comments_count = Comment.query.filter_by(listing_id=self.id).count()
            db.session.add(self)
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Best effort; counts may lag on error
            pass

    def get_recent_comments(self, limit=3):
        """Return up to N newest comments for card preview (read-only)."""
        from app.models.comment import Comment
        try:
            return Comment.query.filter_by(listing_id=self.id).order_by(Comment.created_at.desc()).limit(limit).all()
        except Exception:
            return []


# ============================================================
# Automatic expires_at enforcement (spec 2026-06-29)
# Set expires_at = created_at + 7 days for every new listing.
# Works even when created_at is populated by column default.
# Repost/boost code explicitly refreshes expires_at.
# ============================================================

@event.listens_for(Listing, 'before_insert')
def set_listing_expires_at(mapper, connection, target):
    """Ensure every newly inserted listing gets a 7-day window from its created_at."""
    if target.expires_at is None:
        base = target.created_at or datetime.utcnow()
        target.expires_at = base + timedelta(days=7)