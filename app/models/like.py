from app import db
from datetime import datetime
from sqlalchemy import UniqueConstraint


class Like(db.Model):
    __tablename__ = 'likes'
    __table_args__ = (
        UniqueConstraint('user_id', 'listing_id', name='_user_listing_like_uc'),
        {'extend_existing': True}
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    listing_id = db.Column(db.Integer, db.ForeignKey('listings.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='likes', lazy=True)
    listing = db.relationship('Listing', back_populates='likes')

    def __repr__(self):
        return f'<Like user={self.user_id} listing={self.listing_id}>'
