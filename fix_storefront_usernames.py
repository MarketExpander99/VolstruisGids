"""
Optional one-time inspection script for business storefront usernames.
Run on prod (or dev) to audit accounts that may be surfaced in directory / "View Store".

Usage:
  python inspect_storefront_usernames.py

It does NOT modify data (read-only). Safe.
If policy ever requires normalization (e.g. strip leading @), add it here under a flag.
"""

from app import create_app, db
from app.models.user import User

app = create_app()
with app.app_context():
    print("=== Business Storefront Username Audit ===")
    print("Looking for users with business indicators (is_business, account_type, business_name)...\n")

    # Match the same OR logic used in directory + api_businesses
    businesses = User.query.filter(
        db.or_(
            User.is_business == True,
            User.account_type == 'business',
            User.business_name.isnot(None)
        )
    ).order_by(User.id).all()

    if not businesses:
        print("No business-like accounts found.")
        exit(0)

    print(f"Found {len(businesses)} candidate business accounts:\n")
    for u in businesses:
        has_at = (u.username or '').startswith('@')
        print(f"  id={u.id:4d}  username={repr(u.username):<20}  @prefix={has_at}")
        print(f"          is_business={getattr(u, 'is_business', None)}  "
              f"account_type={getattr(u, 'account_type', None)}  "
              f"business_name={repr(u.business_name)}")
        print(f"          is_business_account (prop)={u.is_business_account}")
        print("")

    print("=== End of audit ===")
    print("If you see @-prefixed usernames that should be clean, consider a follow-up migration.")
    print("This script performed no writes.")
