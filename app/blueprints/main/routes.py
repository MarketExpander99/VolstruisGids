from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from . import main_bp

@main_bp.route('/')
def index():
    query = request.args.get('q', '')
    area = request.args.get('area', '')
    
    listings = Listing.query.order_by(Listing.created_at.desc())
    
    if query:
        listings = listings.filter(
            Listing.title.ilike(f'%{query}%') | 
            Listing.description.ilike(f'%{query}%')
        )
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

@main_bp.route('/my-listings/delete/<int:listing_id>', methods=['POST'])
@login_required
def delete_listing(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    
    # Security: only owner can delete
    if listing.user_id != current_user.id:
        flash('You can only delete your own listings.', 'danger')
        return redirect(url_for('main.my_listings'))
    
    db.session.delete(listing)
    db.session.commit()
    
    flash('Listing deleted successfully ✅', 'success')
    return redirect(url_for('main.my_listings'))