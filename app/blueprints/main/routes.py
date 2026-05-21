from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from . import main_bp


@main_bp.route('/')
def index():
    return render_template('main/index.html')


@main_bp.route('/api/listings')
def api_listings():
    """AJAX endpoint for dynamic feed"""
    query = request.args.get('q', '').strip()
    post_type = request.args.get('post_type', '')
    town = request.args.get('town', '')

    listings_query = Listing.query.filter_by(is_active=True)

    if query:
        listings_query = listings_query.filter(
            (Listing.title.ilike(f'%{query}%')) |
            (Listing.description.ilike(f'%{query}%'))
        )

    if post_type:
        listings_query = listings_query.filter(Listing.post_type == post_type)

    if town:
        listings_query = listings_query.filter(Listing.location == town)

    listings = listings_query.order_by(Listing.created_at.desc()).limit(24).all()

    listings_data = [{
        'id': l.id,
        'title': l.title,
        'description': l.description[:100] + '...' if l.description else '',
        'price': f"R{l.price}" if l.price and l.price > 0 else '',
        'location': l.location,
        'post_type': l.post_type,
        'photo_url': l.photo_url,
        'detail_url': url_for('listings.detail', listing_id=l.id)
    } for l in listings]

    return jsonify({'listings': listings_data})


@main_bp.route('/profile')
@login_required
def profile():
    """Business / Personal Profile Page"""
    listings = Listing.query.filter_by(user_id=current_user.id)\
        .order_by(Listing.created_at.desc()).all()
    return render_template('main/profile.html', listings=listings)


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
    if listing.user_id != current_user.id:
        flash('You can only delete your own listings.', 'danger')
        return redirect(url_for('main.my_listings'))
    db.session.delete(listing)
    db.session.commit()
    flash('Listing deleted successfully ✅', 'success')
    return redirect(url_for('main.my_listings'))