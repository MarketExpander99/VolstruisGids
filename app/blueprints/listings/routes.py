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

    # Auto-seed categories if table is empty (prevents "categories disappeared" issue)
    if Category.query.count() == 0:
        seed_data = [
            ("Farm Equipment", "Listings for Farm Equipment"),
            ("Livestock & Ostriches", "Listings for Livestock & Ostriches"),
            ("Property & Rentals", "Listings for Property & Rentals"),
            ("Services", "Listings for Services"),
            ("Electronics", "Listings for Electronics"),
            ("Vehicles", "Listings for Vehicles"),
            ("General", "Listings for General"),
            ("Building Materials", "Listings for Building Materials"),
            ("Furniture", "Listings for Furniture"),
            ("Jobs", "Listings for Jobs"),
        ]
        for name, desc in seed_data:
            if not Category.query.filter_by(name=name).first():
                db.session.add(Category(name=name, description=desc))
        db.session.commit()

    form.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    if not form.category.choices:
        form.category.choices = [(-1, "No categories yet — please run seed_categories.py")]

    if request.method == 'GET':
        form.contact_phone.data = getattr(current_user, 'phone', '') or getattr(current_user, 'contact_phone', '')
        form.contact_email.data = current_user.email

    if form.validate_on_submit():
        pref = form.contact_preference.data
        contact_phone = None
        contact_email = None

        if pref == 'email':
            contact_email = form.contact_email.data
        elif pref == 'phone':
            contact_phone = form.contact_phone.data
        else:  # any
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

        # === ROBUST PRICING LOGIC (fixed + range support) ===
        price_type = form.price_type.data or 'fixed'
        if price_type == 'fixed':
            price = form.price.data or 0.0
            min_price = None
            max_price = None
        else:  # range (or future types)
            price = None
            min_price = form.min_price.data
            max_price = form.max_price.data

        listing = Listing(
            title=form.title.data,
            description=form.description.data,
            price=price,
            price_type=price_type,
            min_price=min_price,
            max_price=max_price,
            location=form.town.data,
            area="Western Cape",
            contact_phone=contact_phone,
            contact_email=contact_email,
            category_id=form.category.data,
            user_id=current_user.id,
            photo_url=photo_url,
            allow_comments=form.allow_comments.data,
            post_type=form.post_type.data,
            is_business_ad=current_user.is_business
        )

        try:
            db.session.add(listing)
            db.session.commit()
            flash('Listing created successfully! Your free ad will be live for 7 days.', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving your listing: {str(e)}', 'danger')
            # Re-render form so user can correct and retry
            return render_template('listings/create.html', form=form)

    return render_template('listings/create.html', form=form)


@listings_bp.route('/quick-create', methods=['GET', 'POST'])
@login_required
def quick_create():
    if not current_user.is_business:
        flash('Quick-create is only available to Business accounts.', 'warning')
        return redirect(url_for('listings.create'))

    form = ListingForm()

    # Auto-seed categories if table is empty (prevents "categories disappeared" issue)
    if Category.query.count() == 0:
        seed_data = [
            ("Farm Equipment", "Listings for Farm Equipment"),
            ("Livestock & Ostriches", "Listings for Livestock & Ostriches"),
            ("Property & Rentals", "Listings for Property & Rentals"),
            ("Services", "Listings for Services"),
            ("Electronics", "Listings for Electronics"),
            ("Vehicles", "Listings for Vehicles"),
            ("General", "Listings for General"),
            ("Building Materials", "Listings for Building Materials"),
            ("Furniture", "Listings for Furniture"),
            ("Jobs", "Listings for Jobs"),
        ]
        for name, desc in seed_data:
            if not Category.query.filter_by(name=name).first():
                db.session.add(Category(name=name, description=desc))
        db.session.commit()

    form.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    if not form.category.choices:
        form.category.choices = [(-1, "No categories yet — please run seed_categories.py")]

    if request.method == 'GET':
        form.contact_phone.data = current_user.phone
        form.contact_email.data = current_user.email or ''

    if form.validate_on_submit():
        pref = form.contact_preference.data
        contact_phone = None
        contact_email = None

        if pref == 'email':
            contact_email = form.contact_email.data
        elif pref == 'phone':
            contact_phone = form.contact_phone.data
        else:  # any
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

        # === ROBUST PRICING LOGIC (fixed + range support) ===
        price_type = form.price_type.data or 'fixed'
        if price_type == 'fixed':
            price = form.price.data or 0.0
            min_price = None
            max_price = None
        else:  # range (or future types)
            price = None
            min_price = form.min_price.data
            max_price = form.max_price.data

        listing = Listing(
            title=form.title.data,
            description=form.description.data,
            price=price,
            price_type=price_type,
            min_price=min_price,
            max_price=max_price,
            location=form.town.data,
            area="Western Cape",
            contact_phone=contact_phone,
            contact_email=contact_email,
            category_id=form.category.data,
            user_id=current_user.id,
            photo_url=photo_url,
            allow_comments=form.allow_comments.data,
            post_type=form.post_type.data,
            is_business_ad=True
        )

        try:
            db.session.add(listing)
            db.session.commit()
            flash('Listing saved! Add another one below', 'success')
            return redirect(url_for('listings.quick_create'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving your listing: {str(e)}', 'danger')
            return render_template('listings/quick_create.html', form=form)

    return render_template('listings/quick_create.html', form=form)


@listings_bp.route('/listing/<int:listing_id>')
def detail(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    return render_template('listings/detail.html', listing=listing)