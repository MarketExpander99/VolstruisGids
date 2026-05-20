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
    
    return render_template('main/index.html', 
                           listings=listings, 
                           query=query, 
                           area=area,
                           next_offset=20)

@main_bp.route('/load-more')
def load_more():
    """HTMX endpoint for infinite scroll — returns card fragments + self-updating Load More button"""
    offset = request.args.get('offset', 0, type=int)
    listings = Listing.query.order_by(Listing.created_at.desc()).offset(offset).limit(12).all()
    next_offset = offset + 12
    
    return render_template('main/_listing_cards.html', 
                           listings=listings, 
                           next_offset=next_offset)

@main_bp.route('/my-listings')
@login_required
def my_listings():
    listings = Listing.query.filter_by(user_id=current_user.id)\
        .order_by(Listing.created_at.desc()).all()
    return render_template('main/my_listings.html', listings=listings)