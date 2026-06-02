# fix_db.py
import os
from app import create_app, db

app = create_app()

with app.app_context():
    # Get the database file path
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
        if os.path.exists(db_path):
            print(f"🗑️  Deleting old database: {db_path}")
            os.remove(db_path)
            print("✅ Old database deleted.")
        else:
            print("No existing database file found.")
    else:
        print("Not a SQLite database — skipping file deletion.")

    # Create all tables from the current models (price is now nullable=True)
    print("🔄 Creating fresh tables with correct schema...")
    db.create_all()
    print("✅ Database recreated successfully!")
    print("   → 'price' column is now nullable (supports range pricing).")

print("\n🎉 Done! You can now start your server and test creating a range-priced listing.")