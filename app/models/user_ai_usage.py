"""
UserAIUsage model
Tracks free daily Grok chat quota (2 free per calendar day SAST) + basic rate limit signals.
Per spec: free Grok chat on listing detail + fully-free polish/other with hourly caps.
"""

from app import db
from datetime import datetime, date


class UserAIUsage(db.Model):
    __tablename__ = 'user_ai_usage'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    # Calendar date in Africa/Johannesburg for daily reset at midnight SAST
    usage_date = db.Column(db.Date, nullable=False, index=True)

    # Chat-specific free quota (exactly 2 per day)
    free_chat_used = db.Column(db.Integer, default=0, nullable=False)

    # General counters for monitoring / future extension
    total_ai_calls = db.Column(db.Integer, default=0, nullable=False)

    # Timestamps for rate limiting (hourly windows via queries or updates)
    last_ai_call_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'usage_date', name='uq_user_ai_usage_date'),
    )

    def __repr__(self):
        return f'<UserAIUsage user={self.user_id} date={self.usage_date} free_chat={self.free_chat_used}>'
