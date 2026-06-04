from datetime import datetime
from app import db

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    listings = db.relationship('Listing', backref='category', lazy='dynamic')
    
    def __repr__(self):
        return f'<Category {self.name}>'

# Canonical list of categories for Klein Karoo classifieds (idempotent seeding)
SEED_CATEGORIES = [
    ("Accommodation", "Listings for Accommodation & Stays"),
    ("Agriculture & Produce", "Listings for Agriculture, Farming & Produce"),
    ("Automotive", "Listings for Automotive, Vehicles & Mechanics"),
    ("Building Materials & Construction", "Listings for Building, Construction & Materials"),
    ("Electronics", "Listings for Electronics & Appliances"),
    ("Farm Equipment", "Listings for Farm Equipment & Machinery"),
    ("Farm Work & Labour", "Listings for Farm Work, Labour & Agricultural Jobs"),
    ("Food & Beverages", "Listings for Food, Wine & Beverages"),
    ("Furniture & Home", "Listings for Furniture & Home Goods"),
    ("General", "Listings for General Items"),
    ("Jobs & Employment", "Listings for Jobs & Employment Opportunities"),
    ("Livestock & Ostriches", "Listings for Livestock & Ostriches"),
    ("Property & Rentals", "Listings for Property & Rentals"),
    ("Services", "Listings for Services & Repairs"),
    ("Tourism & Hospitality", "Listings for Tourism, Hospitality & Experiences"),
    ("Vehicles", "Listings for Vehicles & Transport"),
]

def seed_categories():
    """Idempotent seeding of default categories. Call anytime to add missing ones."""
    added = 0
    for name, desc in SEED_CATEGORIES:
        if not Category.query.filter_by(name=name).first():
            cat = Category(name=name, description=desc)
            db.session.add(cat)
            added += 1
    if added > 0:
        db.session.commit()
    return added