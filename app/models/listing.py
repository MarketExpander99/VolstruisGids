from app import db
from datetime import datetime

class Listing(db.Model):
    __tablename__ = 'listings'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=True)
    is_business_ad = db.Column(db.Boolean, default=False)
    photos = db.Column(db.JSON, default=list)
    area = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='listings')

    def __repr__(self):
        return f'<Listing {self.title}>'