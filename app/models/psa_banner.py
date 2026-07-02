from datetime import datetime
from app import db


class PSABanner(db.Model):
    __tablename__ = 'psa_banners'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)

    # banner_type: 'alert', 'psa', 'news', 'howto', 'info'
    banner_type = db.Column(db.String(50), default='info', nullable=False)

    # color preset for styling: 'danger', 'warning', 'info', 'success', 'primary', 'dark'
    color = db.Column(db.String(50), default='info', nullable=False)

    active = db.Column(db.Boolean, default=True, nullable=False)
    priority = db.Column(db.Integer, default=0, nullable=False)  # higher = shown first

    link = db.Column(db.String(500), nullable=True)  # optional URL (internal or external)

    expiry = db.Column(db.DateTime, nullable=True)  # optional expiry (inclusive)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<PSABanner {self.id}: {self.title[:40]}>'

    @property
    def is_expired(self):
        """True if an expiry is set and it is in the past."""
        if not self.expiry:
            return False
        return self.expiry <= datetime.utcnow()

    def is_currently_active(self):
        """Considers active flag + expiry."""
        return bool(self.active) and not self.is_expired

    def get_icon(self):
        """Simple icon suggestion based on type."""
        icons = {
            'alert': 'bi-exclamation-triangle-fill',
            'psa': 'bi-megaphone-fill',
            'news': 'bi-newspaper',
            'howto': 'bi-lightbulb-fill',
            'info': 'bi-info-circle-fill',
        }
        return icons.get((self.banner_type or '').lower(), 'bi-info-circle-fill')
