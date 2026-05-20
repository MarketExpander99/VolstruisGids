import os
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.listing import Listing
from app.models.category import Category
from .forms import ListingForm
from . import listings_bp

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@listings_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = ListingForm()
    # Populate categories for select (safe fallback)
    categories = Category.query.order_by(Category.name_en).all()
    form.category.choices = [(c.id, c.name_en) for c in categories] if categories else [(1, 'General')]

    if form.validate_on_submit():
        # Photo upload handling (max 6)
        photos = []
        if 'photos' in request.files:
            uploaded_files = request.files.getlist('photos')
            for file in uploaded_files[:6]:
                if file and allowed_file(file.filename):
                    # Unique filename to avoid collisions
                    timestamp = datetime.now().timestamp()
                    filename = secure_filename(f"{current_user.id}_{timestamp}_{file.filename}")
                    upload_path = os.path.join(current_app.root_path, 'static', 'uploads', filename)
                    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                    file.save(upload_path)
                    photos.append(f"uploads/{filename}")

        listing = Listing(
            user_id=current_user.id,
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            location=form.area.data,          # reuse area for existing nullable=False field
            area=form.area.data,
            is_business_ad=getattr(current_user, 'is_business', False),
            photos=photos,
            category_id=form.category.data
        )
        db.session.add(listing)
        db.session.commit()
        flash('Ad posted successfully! Photos uploaded.', 'success')
        return redirect(url_for('main.index'))

    return render_template('listings/create.html', form=form)

@listings_bp.route('/<int:listing_id>')
def detail(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    return render_template('listings/detail.html', listing=listing)