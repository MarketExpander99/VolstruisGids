from flask import render_template
from flask_login import login_required, current_user
from app.models.listing import Listing
from . import main_bp

@main_bp.route('/')
def index():
    # Show latest listings
    listings = Listing.query.order_by(Listing.created_at.desc()).limit(20).all()
    return render_template('main/index.html', listings=listings, title="VolstruisGids")

@main_bp.route('/feed')
@login_required
def feed():
    listings = Listing.query.order_by(Listing.created_at.desc()).all()
    return render_template('main/feed.html', listings=listings)