from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from app.models.category import Category, seed_categories
from .forms import ListingForm
from app.blueprints.messages.forms import MessageForm   # for private message modal CSRF + fields on detail page
from . import listings_bp
import os
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime, date
from app.models.credit_transaction import CreditTransaction
import requests
import json as pyjson

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


@listings_bp.route('/improve-with-ai', methods=['POST'])
@login_required
def improve_with_ai():
    """One powerful AI improvement for the whole listing (professional ad + realistic Klein Karoo market price)."""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    post_type = data.get('post_type', '')
    category_id = data.get('category_id')
    town = (data.get('town') or '').strip()
    price = data.get('price') or ''

    if not title and not description:
        return jsonify({'error': 'Please add a title or description first.'}), 400

    # Daily quota check (2 free, then 8 credits)
    today = date.today()
    ai_uses_today = CreditTransaction.query.filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.transaction_type.in_(['ai_improve', 'ai_improve_free']),
        db.func.date(CreditTransaction.created_at) == today
    ).count()

    is_free = ai_uses_today < 2
    cost = 0 if is_free else 8

    if not is_free and current_user.credit_balance < cost:
        return jsonify({
            'error': f'Not enough credits. After 2 free daily uses, this costs {cost} credits.'
        }), 402

    # === Grok Prompt - Professional Selling Ad + Realistic Klein Karoo Market Price ===
    try:
        grok_api_key = os.environ.get('GROK_API_KEY')
        if not grok_api_key:
            return jsonify({'error': 'AI service not configured. Add GROK_API_KEY to .env'}), 500

        category_name = ""
        if category_id:
            cat = Category.query.get(category_id)
            if cat:
                category_name = cat.name

        prompt = f"""You are a professional classifieds copywriter and local market pricing expert for VolstruisGids, serving the Klein Karoo towns (Oudtshoorn, Ladismith, Calitzdorp, etc.) in the Western Cape, South Africa.

Your goal: Create a clean, professional, fact-based listing that will actually help this item sell quickly. Stay honest, local-sounding, and trustworthy. Never overpromise.

Key context for this listing:
- Post type: {post_type}
- Category: {category_name}
- Town / Area: {town}
- Original Title: {title}
- Original Description: {description}
- User's current price input (if provided): {price if price else 'not specified by user'}

For the pricing suggestion:
You must suggest a single realistic **suggested_price** (integer in ZAR) that reflects current fair market value for this specific item in the Klein Karoo / rural Western Cape second-hand market.

Consider these real market variables when deciding the price:
- Typical prices for similar items in this category in small Karoo towns (lower than Cape Town metro due to smaller buyer pool and logistics).
- Item condition, age, brand, and features described (or implied).
- Local demand drivers: agricultural/farming season, tourism/high season, school holidays, or economic factors in the region.
- Supply: how common this item is locally (e.g. bakkie parts, farming equipment, household appliances, furniture, livestock-related).
- Quick-sale pricing psychology for classifieds platforms — slightly competitive but fair so it sells without long wait.
- If post_type is 'wanted': suggest a realistic offer price a buyer would make.
- If 'rental' or 'services': the rate should be sensible per the duration unit.

DO NOT default to any example number like 1250 or copy from previous responses. Base it purely on your trained knowledge of South African rural marketplace values in the Western Cape Karoo region. Make it specific to the described item.

Return ONLY valid JSON with these exact keys (no extra text, no markdown):

{{
  "improved_title": "Clear, professional, benefit-focused title (max 85 characters, include key specs or town if helpful)",
  "improved_description": "Professional, scannable description. Use short paragraphs or bullet points where helpful. Highlight real benefits, condition, location advantages, and call-to-action. Keep it trustworthy and easy to read. Max 380 words.",
  "suggested_price": <the integer ZAR price you determined from market analysis>,
  "price_reason": "1-2 sentences explaining the suggested price with reference to specific local Klein Karoo market factors (e.g. comparable farm gear prices in Oudtshoorn area this season, demand for this item type, condition-based adjustment)."
}}"""

        headers = {
            "Authorization": f"Bearer {grok_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "grok-3-latest",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.6,
            "max_tokens": 950
        }

        resp = requests.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']

        cleaned = content.strip().replace('```json', '').replace('```', '').strip()
        improved = pyjson.loads(cleaned)

        return jsonify({
            'success': True,
            'improved_title': improved.get('improved_title', title),
            'improved_description': improved.get('improved_description', description),
            'suggested_price': improved.get('suggested_price'),
            'price_reason': improved.get('price_reason', ''),
            'is_free': is_free,
            'credits_used': cost,
            'remaining_credits': current_user.credit_balance - cost if not is_free else current_user.credit_balance,
            'uses_today': ai_uses_today + 1
        })

    except Exception as e:
        return jsonify({'error': f'AI temporarily unavailable. ({str(e)})'}), 500

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
        selected = form.contact_methods.data or []
        contact_phone = form.contact_phone.data if 'phone' in selected else None
        contact_email = form.contact_email.data if 'email' in selected else None
        contact_methods = ','.join(selected) if selected else 'dm,email,phone'

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
            contact_methods=contact_methods,
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
        # Prefill multi-select, with backward compat for old listings (no contact_methods yet)
        if listing.contact_methods:
            form.contact_methods.data = [m.strip() for m in listing.contact_methods.split(',') if m.strip()]
        else:
            methods = ['dm']
            if listing.contact_email:
                methods.append('email')
            if listing.contact_phone:
                methods.append('phone')
            form.contact_methods.data = methods

    if form.validate_on_submit():
        selected = form.contact_methods.data or []
        contact_phone = form.contact_phone.data if 'phone' in selected else None
        contact_email = form.contact_email.data if 'email' in selected else None
        contact_methods = ','.join(selected) if selected else 'dm,email,phone'

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
        listing.contact_methods = contact_methods
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
        selected = form.contact_methods.data or []
        contact_phone = form.contact_phone.data if 'phone' in selected else None
        contact_email = form.contact_email.data if 'email' in selected else None
        contact_methods = ','.join(selected) if selected else 'dm,email,phone'

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
            contact_methods=contact_methods,
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


@listings_bp.route('/boost/<int:listing_id>', methods=['POST'])
@login_required
def boost(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    if current_user.id != listing.user_id:
        flash('You can only boost your own listings.', 'danger')
        return redirect(url_for('listings.detail', listing_id=listing.id))

    try:
        listing.is_promoted = True
        listing.last_reposted_at = datetime.utcnow()
        db.session.commit()
        flash('Listing boosted for 7 days! It now has a PROMOTED badge and extra visibility.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error boosting your listing: {str(e)}', 'danger')

    return redirect(url_for('listings.detail', listing_id=listing.id))


@listings_bp.route('/listing/<int:listing_id>')
def detail(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    listing.views = (listing.views or 0) + 1
    db.session.commit()
    # Prepare message form (only for the private DM modal when the listing allows DM and user is eligible)
    # This ensures proper CSRF token via hidden_tag() and prefilled hidden fields.
    message_form = None
    cm = (listing.contact_methods or '').strip()
    methods = [m.strip() for m in cm.split(',') if m.strip()] if cm else ['dm', 'email', 'phone']
    if 'dm' in methods and current_user.is_authenticated and current_user.id != listing.user_id:
        message_form = MessageForm()
        message_form.receiver_id.data = listing.user_id
        message_form.listing_id.data = listing.id

    return render_template('listings/detail.html', listing=listing, message_form=message_form)