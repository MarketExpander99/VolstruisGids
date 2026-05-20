# seed_categories.py
from app import create_app, db
from app.models.category import Category

app = create_app()

with app.app_context():
    if Category.query.count() == 0:
        categories = [
            "Farm Equipment", "Livestock & Ostriches", "Property & Rentals",
            "Services", "Electronics", "Vehicles", "General", "Building Materials",
            "Furniture", "Jobs"
        ]
        for name in categories:
            cat = Category(name=name, description=f"Listings for {name}")
            db.session.add(cat)
        db.session.commit()
        print("✅ Default categories seeded successfully!")
    else:
        print("Categories already exist.")