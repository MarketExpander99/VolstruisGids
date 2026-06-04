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
from datetime import datetime
from app.models.credit_transaction import CreditTransaction

UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_image_to_square(image_path, size=800, bg_color=(250, 244, 235)):
    """
    Resize image to fit inside a square canvas WITHOUT cropping.
    Adds letterboxing (whitespace) so the full original image is always visible.
    """
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.thumbnail((size, size), Image.Resampling.LANCZOS)

            new_img = Image.new("RGB", (size, size), bg_color)
            offset = ((size - img.width) // 2, (size - img.height) // 2)
            new_img.paste(img, offset)

            new_img.save(image_path, quality=92)
        return True
    except Exception as e:
        print(f"Image resize error: {e}")
        return False


@listings_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = ListingForm()

    # Auto-seed categories if table is empty
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
        else:
            contact_phone = form.contact_phone.data
            contact_email = form.contact_email.data

        # === PHOTO UPLOAD (now correctly inside the function) ===
        photo_url = None
        if form.photo.data and allowed_file(form.photo.data.filename):
            filename = secure_filename(form.photo.data.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            form.photo.data.save(filepath)
            resize_image_to_square(filepath)
            photo_url = f'/static/uploads/{filename}'

        # Pricing logic
        price_type = form.price_type.data or 'fixed'
        if price_type == 'fixed':
            price = form.price.data or 0.0
            min_price = None
            max_price = None
        else:
            price = 0.0  # legacy placeholder (NOT NULL in some DBs); range uses min/max for display
            min_price = form.min_price.data
            max_price = form.max_price.data

        # Credit logic
        posts_today = getattr(current_user, 'posts_today', 0) or 0
        is_business = current_user.account_type == 'business' or current_user.is_business

        if current_user.account_type == 'personal' and posts_today < 1:
            required_credits = 0
            listing_type = 'normal'
            current_user.posts_today = posts_today + 1
            txn = CreditTransaction(
                user_id=current_user.id,
                amount=0,
                transaction_type='free_quota',
                reference=f'free_quota_{datetime.utcnow().isoformat()}'
            )
            db.session.add(txn)
        else:
            required_credits = 2 if is_business else 1
            listing_type = 'super' if is_business else 'normal'

            if current_user.credit_balance < required_credits:
                flash(
                    f'Not enough credits. This {"super/business" if is_business else "normal"} listing requires {required_credits} credit(s). '
                    'Please buy more credits to continue.',
                    'warning'
                )
                return render_template('listings/create.html', form=form)

            current_user.credit_balance -= required_credits
            txn = CreditTransaction(
                user_id=current_user.id,
                amount=-required_credits,
                transaction_type='listing',
                reference=f'listing_create_{datetime.utcnow().isoformat()}'
            )
            db.session.add(txn)

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
            is_business_ad=current_user.is_business,
            listing_type=listing_type
        )

        try:
            db.session.add(listing)
            db.session.commit()

            if required_credits == 0:
                flash('Listing created successfully using your free daily quota! It will be live for 7 days.', 'success')
            else:
                flash(
                    f'Listing created successfully! {required_credits} credit(s) deducted. '
                    f'New balance: {current_user.credit_balance}',
                    'success'
                )
            return redirect(url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving your listing: {str(e)}', 'danger')
            return render_template('listings/create.html', form=form)

    return render_template('listings/create.html', form=form)


@listings_bp.route('/quick-create', methods=['GET', 'POST'])
@login_required
def quick_create():
    if not current_user.is_business:
        flash('Quick-create is only available to Business accounts.', 'warning')
        return redirect(url_for('listings.create'))

    form = ListingForm()

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
        else:
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

        price_type = form.price_type.data or 'fixed'
        if price_type == 'fixed':
            price = form.price.data or 0.0
            min_price = None
            max_price = None
        else:
            price = 0.0  # legacy placeholder (NOT NULL in some DBs); range uses min/max for display
            min_price = form.min_price.data
            max_price = form.max_price.data

        required_credits = 2
        if current_user.credit_balance < required_credits:
            flash(
                f'Not enough credits. Quick-create (super/business) listings require {required_credits} credits. '
                'Please buy more credits.',
                'warning'
            )
            return render_template('listings/quick_create.html', form=form)

        current_user.credit_balance -= required_credits
        txn = CreditTransaction(
            user_id=current_user.id,
            amount=-required_credits,
            transaction_type='listing',
            reference=f'quick_listing_{datetime.utcnow().isoformat()}'
        )
        db.session.add(txn)

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
            is_business_ad=True,
            listing_type='super'
        )

        try:
            db.session.add(listing)
            db.session.commit()
            flash(
                f'Listing saved! 2 credits deducted. New balance: {current_user.credit_balance}. Add another one below.',
                'success'
            )
            return redirect(url_for('listings.quick_create'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving your listing: {str(e)}', 'danger')
            return render_template('listings/quick_create.html', form=form)

    return render_template('listings/quick_create.html', form=form)


@listings_bp.route('/listing/<int:listing_id>')
def detail(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    listing.views = (listing.views or 0) + 1
    db.session.commit()
    return render_template('listings/detail.html', listing=listing)