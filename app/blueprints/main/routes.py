from flask import render_template, request, abort
from flask_login import login_required, current_user
from app.models.listing import Listing
from . import main_bp

@main_bp.route('/')
def index():
    query = request.args.get('q', '')
    area = request.args.get('area', '')
    
    listings = Listing.query.filter_by(is_active=True).order_by(Listing.created_at.desc())
    
    if query:
        listings = listings.filter(
            Listing.title.ilike(f'%{query}%') | 
            Listing.description.ilike(f'%{query}%')
        )
    if area:
        listings = listings.filter_by(area=area)
    
    listings = listings.limit(20).all()
    return render_template('main/index.html', listings=listings, query=query, area=area)

@main_bp.route('/listing/<int:listing_id>')
def listing_detail(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    if not listing.is_active:
        abort(404)
    
    # Increment views
    listing.views += 1
    listing.save()  # or db.session.commit() if you prefer
    
    return render_template('main/listing_detail.html', listing=listing)

@main_bp.route('/my-listings')
@login_required
def my_listings():
    listings = Listing.query.filter_by(user_id=current_user.id, is_active=True)\
        .order_by(Listing.created_at.desc()).all()
    return render_template('main/my_listings.html', listings=listings)