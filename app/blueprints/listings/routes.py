from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from app.models.category import Category
from .forms import ListingForm
from . import listings_bp
import os
from werkzeug.utils import secure_filename
from PIL import Image

UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def resize_image_to_square(image_path, size=800):
    """Enforce perfect 1:1 square (center crop + resize) for optimal display."""
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

@listings_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = ListingForm()
    form.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    
    if not form.category.choices:
        form.category.choices = [(-1, "No categories yet — please run seed_categories.py")]

    if form.validate_on_submit():
        pref = form.contact_preference.data
        contact_phone = None
        contact_email = None

        is_premium = getattr(current_user, 'is_premium', False) or getattr(current_user, 'premium', False)
        
        if pref in ('dm', 'any') and not is_premium:
            flash('📩 DM and Any options are premium features. Please upgrade or choose Email/Phone only.', 'danger')
            return render_template('listings/create.html', form=form)

        if pref == 'email':
            contact_email = form.contact_email.data
        elif pref == 'phone':
            contact_phone = form.contact_phone.data
        elif pref == 'dm':
            pass
        else:  # 'any'
            contact_phone = form.contact_phone.data
            contact_email = form.contact_email.data

        photo_url = None
        if form.photo.data and allowed_file(form.photo.data.filename):
            filename = secure_filename(form.photo.data.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            form.photo.data.save(filepath)
            resize_image_to_square(filepath)
            photo_url = f'/static/uploads/{filename}'

        listing = Listing(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            location=form.town.data,
            area="Western Cape",
            contact_phone=contact_phone,
            contact_email=contact_email,
            category_id=form.category.data,
            user_id=current_user.id,
            photo_url=photo_url
        )
        
        db.session.add(listing)
        db.session.commit()
        
        flash('✅ Listing created successfully! Your free ad will be live for 7 days.', 'success')
        return redirect(url_for('main.index'))
    
    return render_template('listings/create.html', form=form)


@listings_bp.route('/listing/<int:listing_id>')
def detail(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    return render_template('listings/detail.html', listing=listing)