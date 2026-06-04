from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from app.models.category import Category, seed_categories
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

    # Auto-seed categories (idempotent)
    seed_categories()

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

        # === PHOTO UPLOAD (supports multiple; first becomes photo_url, rest in photo_urls; extra photo = +1 credit) ===
        photo_url = None
        photo_urls_list = []
        if form.photo.data:
            files = form.photo.data if isinstance(form.photo.data, (list, tuple)) else [form.photo.data]
            for f in files:
                if f and getattr(f, 'filename', None) and allowed_file(f.filename):
                    filename = secure_filename(f.filename)
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    f.save(filepath)
                    resize_image_to_square(filepath)
                    url = f'/static/uploads/{filename}'
                    if photo_url is None:
                        photo_url = url
                    else:
                        photo_urls_list.append(url)
        photo_urls = ','.join(photo_urls_list) if photo_urls_list else None

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

        # Rental fields (if applicable)
        rental_duration = form.rental_duration.data if form.post_type.data == 'rental' else None
        rental_duration_unit = form.rental_duration_unit.data if form.post_type.data == 'rental' else None

        # Extra credits for additional photos (first photo included; +1 credit per extra)
        num_extra_photos = len(photo_urls_list) if 'photo_urls_list' in locals() else 0

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
            base_credits = 2 if is_business else 1
            extra_photo_credits = num_extra_photos
            required_credits = base_credits + extra_photo_credits
            listing_type = 'super' if is_business else 'normal'

            if current_user.credit_balance < required_credits:
                if extra_photo_credits > 0:
                    msg = f'Not enough credits. This {"super/business" if is_business else "normal"} listing requires {required_credits} credit(s). ({extra_photo_credits} extra for additional photos)'
                else:
                    msg = f'Not enough credits. This {"super/business" if is_business else "normal"} listing requires {required_credits} credit(s). Please buy more credits to continue.'
                flash(msg, 'warning')
                return render_template('listings/create.html', form=form, editing=False)

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
            photo_urls=photo_urls,
            allow_comments=form.allow_comments.data,
            post_type=form.post_type.data,
            is_business_ad=current_user.is_business,
            listing_type=listing_type,
            rental_duration=rental_duration,
            rental_duration_unit=rental_duration_unit
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
            return render_template('listings/create.html', form=form, editing=False)

    return render_template('listings/create.html', form=form)


@listings_bp.route('/listing/<int:listing_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_listing(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    if listing.user_id != current_user.id:
        flash('You can only edit your own listings.', 'danger')
        return redirect(url_for('main.my_listings'))

    form = ListingForm(obj=listing)

    seed_categories()

    form.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    if not form.category.choices:
        form.category.choices = [(-1, "No categories yet — please run seed_categories.py")]

    if request.method == 'GET':
        # Prefill fields that don't map directly via obj=
        form.town.data = listing.location
        form.category.data = listing.category_id
        form.post_type.data = listing.post_type
        form.price_type.data = listing.price_type or 'fixed'
        if listing.price_type == 'fixed':
            form.price.data = listing.price
        else:
            form.min_price.data = listing.min_price
            form.max_price.data = listing.max_price
        if listing.post_type == 'rental':
            form.rental_duration.data = listing.rental_duration
            form.rental_duration_unit.data = listing.rental_duration_unit or 'day'
        form.contact_phone.data = listing.contact_phone or ''
        form.contact_email.data = listing.contact_email or ''
        form.allow_comments.data = listing.allow_comments if listing.allow_comments is not None else True
        if listing.contact_email and not listing.contact_phone:
            form.contact_preference.data = 'email'
        elif listing.contact_phone and not listing.contact_email:
            form.contact_preference.data = 'phone'
        else:
            form.contact_preference.data = 'any'

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

        # Photo: only replace if new files uploaded
        photo_url = listing.photo_url
        photo_urls = listing.photo_urls
        if form.photo.data:
            files = form.photo.data if isinstance(form.photo.data, (list, tuple)) else [form.photo.data]
            new_photos = []
            for f in files:
                if f and getattr(f, 'filename', None) and allowed_file(f.filename):
                    filename = secure_filename(f.filename)
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    f.save(filepath)
                    resize_image_to_square(filepath)
                    new_photos.append(f'/static/uploads/{filename}')
            if new_photos:
                photo_url = new_photos[0]
                photo_urls = ','.join(new_photos[1:]) if len(new_photos) > 1 else None

        # Pricing
        price_type = form.price_type.data or 'fixed'
        if price_type == 'fixed':
            price = form.price.data or 0.0
            min_price = None
            max_price = None
        else:
            price = 0.0
            min_price = form.min_price.data
            max_price = form.max_price.data

        # Rental
        rental_duration = form.rental_duration.data if form.post_type.data == 'rental' else None
        rental_duration_unit = form.rental_duration_unit.data if form.post_type.data == 'rental' else None

        # Update listing (no credit changes on edit)
        listing.title = form.title.data
        listing.description = form.description.data
        listing.price = price
        listing.price_type = price_type
        listing.min_price = min_price
        listing.max_price = max_price
        listing.location = form.town.data
        listing.area = "Western Cape"
        listing.contact_phone = contact_phone
        listing.contact_email = contact_email
        listing.category_id = form.category.data
        listing.photo_url = photo_url
        listing.photo_urls = photo_urls
        listing.allow_comments = form.allow_comments.data
        listing.post_type = form.post_type.data
        listing.rental_duration = rental_duration
        listing.rental_duration_unit = rental_duration_unit

        try:
            db.session.commit()
            flash('Listing updated successfully!', 'success')
            return redirect(url_for('main.my_listings'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating your listing: {str(e)}', 'danger')
            return render_template('listings/create.html', form=form, listing=listing, editing=True)

    return render_template('listings/create.html', form=form, listing=listing, editing=True)


@listings_bp.route('/quick-create', methods=['GET', 'POST'])
@login_required
def quick_create():
    if not current_user.is_business:
        flash('Quick-create is only available to Business accounts.', 'warning')
        return redirect(url_for('listings.create'))

    form = ListingForm()

    seed_categories()

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

        # === PHOTO UPLOAD (supports multiple; first becomes photo_url, rest in photo_urls; extra photo = +1 credit) ===
        photo_url = None
        photo_urls_list = []
        if form.photo.data:
            files = form.photo.data if isinstance(form.photo.data, (list, tuple)) else [form.photo.data]
            for f in files:
                if f and getattr(f, 'filename', None) and allowed_file(f.filename):
                    filename = secure_filename(f.filename)
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    f.save(filepath)
                    resize_image_to_square(filepath)
                    url = f'/static/uploads/{filename}'
                    if photo_url is None:
                        photo_url = url
                    else:
                        photo_urls_list.append(url)
        photo_urls = ','.join(photo_urls_list) if photo_urls_list else None

        price_type = form.price_type.data or 'fixed'
        if price_type == 'fixed':
            price = form.price.data or 0.0
            min_price = None
            max_price = None
        else:
            price = 0.0  # legacy placeholder (NOT NULL in some DBs); range uses min/max for display
            min_price = form.min_price.data
            max_price = form.max_price.data

        # Rental fields (if applicable)
        rental_duration = form.rental_duration.data if form.post_type.data == 'rental' else None
        rental_duration_unit = form.rental_duration_unit.data if form.post_type.data == 'rental' else None

        required_credits = 2
        num_extra_photos = len(photo_urls_list)
        extra_photo_credits = num_extra_photos
        total_required = required_credits + extra_photo_credits
        if current_user.credit_balance < total_required:
            if extra_photo_credits > 0:
                msg = f'Not enough credits. Quick-create (super/business) listings require {total_required} credits. ({extra_photo_credits} extra for additional photos)'
            else:
                msg = f'Not enough credits. Quick-create (super/business) listings require {total_required} credits. Please buy more credits.'
            flash(msg, 'warning')
            return render_template('listings/quick_create.html', form=form)

        current_user.credit_balance -= total_required
        txn = CreditTransaction(
            user_id=current_user.id,
            amount=-total_required,
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
            photo_urls=photo_urls,
            allow_comments=form.allow_comments.data,
            post_type=form.post_type.data,
            is_business_ad=True,
            listing_type='super',
            rental_duration=rental_duration,
            rental_duration_unit=rental_duration_unit
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