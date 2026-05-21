from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from sqlalchemy.orm import joinedload
from . import main_bp
import os
from werkzeug.utils import secure_filename
from PIL import Image

UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def resize_image_to_square(image_path, size=400):
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if width > height:
                left = (width - height) // 2
                top = 0
                right = left + height
                bottom = height
            else:
                left = 0
                top = (height - width) // 2
                right = width
                bottom = top + width
            img = img.crop((left, top, right, bottom))
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            img.save(image_path)
        return True
    except Exception:
        return False

@main_bp.route('/')
def index():
    return render_template('main/index.html')


@main_bp.route('/api/listings')
def api_listings():
    """AJAX endpoint for dynamic feed + infinite scroll + business branding"""
    query = request.args.get('q', '').strip()
    post_type = request.args.get('post_type', '')
    town = request.args.get('town', '')
    page = int(request.args.get('page', 1))
    per_page = 12

    listings_query = Listing.query.options(joinedload(Listing.user)).filter_by(is_active=True)

    if query:
        listings_query = listings_query.filter(
            (Listing.title.ilike(f'%{query}%')) |
            (Listing.description.ilike(f'%{query}%'))
        )

    if post_type:
        listings_query = listings_query.filter(Listing.post_type == post_type)

    if town:
        listings_query = listings_query.filter(Listing.location == town)

    listings = listings_query.order_by(Listing.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)

    listings_data = [{
        'id': l.id,
        'title': l.title,
        'description': l.description[:100] + '...' if l.description else '',
        'price': f"R{l.price}" if l.price and l.price > 0 else '',
        'location': l.location,
        'post_type': l.post_type,
        'photo_url': l.photo_url,
        'detail_url': url_for('listings.detail', listing_id=l.id),
        'is_business_ad': l.is_business_ad,
        'business_name': l.user.business_name if l.is_business_ad and l.user else None,
        'business_logo': l.user.profile_pic if l.is_business_ad and l.user and l.user.profile_pic else None
    } for l in listings.items]

    return jsonify({
        'listings': listings_data,
        'has_more': listings.has_next,
        'next_page': page + 1 if listings.has_next else None
    })


@main_bp.route('/profile')
@login_required
def profile():
    listings = Listing.query.filter_by(user_id=current_user.id)\
        .order_by(Listing.created_at.desc()).all()
    return render_template('main/profile.html', listings=listings)


@main_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Business + Personal Profile Edit with logo upload"""
    if request.method == 'POST':
        # Update text fields
        current_user.business_name = request.form.get('business_name') if current_user.is_business else None
        current_user.bio = request.form.get('bio')
        current_user.location = request.form.get('location')

        # Logo upload
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename and allowed_file(file.filename):
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                filename = secure_filename(f"profile_{current_user.id}_{file.filename}")
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                resize_image_to_square(filepath)
                current_user.profile_pic = f'/static/uploads/{filename}'

        db.session.commit()
        flash('✅ Profile updated successfully!', 'success')
        return redirect(url_for('main.profile'))

    return render_template('main/profile.html', listings=[], edit_mode=True)


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