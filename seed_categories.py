# seed_categories.py
from app import create_app
from app.models.category import seed_categories

app = create_app()

with app.app_context():
    added = seed_categories()
    if added > 0:
        print(f"✅ Seeded {added} new categories successfully!")
    else:
        print("✅ All categories already exist. Nothing to add.")