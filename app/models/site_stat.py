from datetime import datetime
from app import db


class SiteStat(db.Model):
    __tablename__ = 'site_stats'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Integer, default=0, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get_or_create(key, default=0):
        """Get existing stat or create a new one with the given default."""
        stat = SiteStat.query.filter_by(key=key).first()
        if not stat:
            stat = SiteStat(key=key, value=default)
            db.session.add(stat)
            db.session.commit()
        return stat

    @staticmethod
    def increment(key, amount=1):
        """Atomically increment (best-effort) and return the new value."""
        stat = SiteStat.get_or_create(key, 0)
        stat.value = (stat.value or 0) + amount
        db.session.commit()
        return stat.value

    @staticmethod
    def get_value(key, default=0):
        """Return current value for key, or default if never recorded."""
        stat = SiteStat.query.filter_by(key=key).first()
        return stat.value if stat else default
