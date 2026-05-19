from flask import render_template, request
from flask_login import login_required, current_user
from app.models.listing import Listing
from . import main_bp

@main_bp.route('/')
def index():
    query = request.args.get('q', '')
    area = request.args.get('area', '')
    
    listings = Listing.query.order_by(Listing.created_at.desc())
    
    if query:
        listings = listings.filter(Listing.title.ilike(f'%{query}%') | 
                                  Listing.description.ilike(f'%{query}%'))
    if area:
        listings = listings.filter_by(area=area)
    
    listings = listings.limit(20).all()
    
    return render_template('main/index.html', listings=listings, query=query, area=area)

@main_bp.route('/my-listings')
@login_required
def my_listings():
    listings = Listing.query.filter_by(user_id=current_user.id)\
        .order_by(Listing.created_at.desc()).all()
    return render_template('main/my_listings.html', listings=listings)