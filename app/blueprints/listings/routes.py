from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from app.models.category import Category, seed_categories
from .forms import ListingForm
from app.blueprints.messages.forms import MessageForm
from . import listings_bp
import os
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime, date, timedelta
from decimal import Decimal
from app.models.credit_transaction import CreditTransaction
from app.models.user_ai_usage import UserAIUsage
import requests
import json as pyjson
import re
from sqlalchemy import func
from sqlalchemy.orm import joinedload

UPLOAD_FOLDER = 'app/static/uploads'  # fallback; prefer current_app.config['UPLOAD_FOLDER']
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_image_to_square(image_path, size=800, bg_color=(250, 244, 235)):
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
    """Grok polish: ONLY title + description. Separate locally-researched price recommendation.
    Price fields are never mutated. Follows VolstruisGids Klein Karoo expert prompt.
    """
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    post_type = data.get('post_type', '')
    category_id = data.get('category_id')
    town = (data.get('town') or '').strip()
    price = data.get('price') or ''
    price_type = (data.get('price_type') or 'fixed').strip()

    if not title and not description:
        return jsonify({'error': 'Please add a title or description first.'}), 400

    # Polish with Grok is COMPLETELY FREE (per 2026-06-20 spec). Only hourly rate limit.
    try:
        allowed, rate_msg = current_user.check_ai_rate_limit(action='polish', max_per_hour=8)
        if not allowed:
            return jsonify({'error': rate_msg}), 429
    except Exception:
        # Table or query hiccup on first run — allow the (free) request and let later calls settle
        pass

    # Record usage (for rate limit window + monitoring). No credit deduction ever for polish.
    current_user.record_ai_action()
    tx = CreditTransaction(
        user_id=current_user.id,
        amount=Decimal('0'),
        transaction_type='ai_improve_free',
        reference='polish_free'
    )
    db.session.add(tx)
    db.session.commit()

    try:
        grok_api_key = current_app.config.get('GROK_API_KEY')
        grok_api_url = current_app.config.get('GROK_API_URL', 'https://api.x.ai/v1/chat/completions')
        grok_model = current_app.config.get('GROK_MODEL', 'grok-3')

        if not grok_api_key:
            return jsonify({'error': 'AI service not configured. Add GROK_API_KEY to .env'}), 500

        category_name = ""
        if category_id:
            cat = Category.query.get(category_id)
            if cat:
                category_name = cat.name

        # === NEW SPEC PROMPT: Title + Description only. Separate researched price insight. ===
        prompt = f"""You are "VolstruisGids Klein Karoo Market Expert" — a trusted, no-nonsense advisor who has helped hundreds of local sellers in Oudtshoorn, Ladismith, Calitzdorp, De Rust, and the surrounding Western Cape farms get fair prices and quick sales on VolstruisGids.

You deeply understand:
- Local buyer behaviour (cash buyers, farm collections, tourism trade, agricultural community needs)
- Seasonal demand (hunting season, school holidays, harvest time, winter vs summer)
- What actually sells fast vs what lingers in the Klein Karoo classifieds market
- Realistic price ranges for used goods in this region (not Johannesburg or Cape Town prices)

TASK: Polish a draft classifieds listing.

INPUTS YOU WILL RECEIVE:
- category
- draft_title (may be rough)
- draft_description (may be short or unstructured)
- draft_price (user's current number or range — treat as reference only)
- price_type ("fixed", "range", or null)
- town_or_area (e.g. "Ladismith", "Oudtshoorn", "Klein Karoo")
- condition (if mentioned: new, like-new, good, fair, needs work)

STRICT RULES:
1. TITLE (polished_title)
   - Make it clear, specific, and searchable.
   - Max ~70 characters.
   - Include key attributes buyers search for (brand, size, material, condition signal).
   - Honest and professional — no clickbait.

2. DESCRIPTION (polished_description)
   - Rewrite into scannable, friendly paragraphs or short bullets.
   - Lead with the strongest selling point.
   - Mention condition, age, reason for selling, and practical local details (collection, delivery radius, cash/EFT, farm access).
   - End with a warm, low-pressure CTA.
   - 80–160 words ideal. Natural South African English.

3. PRICE RECOMMENDATION (completely separate from title/desc polish)
   - Base your recommendation on:
     * Real market value for this category + condition in the Klein Karoo right now
     * Local supply/demand signals you know
     * Practical factors (pickup convenience, tourism route proximity, farm vs town)
   - **NEVER** suggest a price simply by taking "X% less than what the user typed". That is lazy and forbidden.
   - Provide a single recommended price (or tight range if price_type=range).
   - Write a short, credible "why" explanation (2–4 sentences) that references local context.
   - Add a confidence level: High / Medium / Low + one-line note.
   - If the draft has very little information, still give a solid category benchmark and note that more details would sharpen the recommendation.

4. GOOGLE SEO OPTIMIZATION (important for VolstruisGids)
   - Naturally weave in the town/area so the final listing performs well in our dynamic meta title, description, and keywords on the detail page.
   - Use clear, searchable phrasing in the title (brand/model/year/condition + location signal is ideal).
   - In the description, mention key buyer search terms naturally (never stuff keywords).
   - The goal is higher visibility in local Klein Karoo / Western Cape searches on Google while staying honest and buyer-friendly.
   - This helps the seller's ad get found faster.

5. OUTPUT FORMAT — ONLY valid JSON, nothing else:
{{
  "polished_title": "string",
  "polished_description": "string (use \\n for line breaks)",
  "price_recommendation": {{
    "recommended_price": number,
    "range_low": number or null,
    "range_high": number or null,
    "currency": "ZAR",
    "why": "string (local market reasoning)",
    "confidence": "High" | "Medium" | "Low",
    "local_context": "string (optional extra Klein Karoo flavour)"
  }}
}}

Key context for this request:
- Post type: {post_type}
- Category: {category_name}
- Town / Area: {town}
- Draft Title: {title}
- Draft Description: {description}
- Draft price input: {price if price else 'not provided'}
- Price type: {price_type}
"""

        headers = {
            "Authorization": f"Bearer {grok_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": grok_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.6,
            "max_tokens": 1100
        }

        resp = requests.post(grok_api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']

        cleaned = content.strip().replace('```json', '').replace('```', '').strip()
        try:
            improved = pyjson.loads(cleaned)
        except Exception:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if match:
                improved = pyjson.loads(match.group(0))
            else:
                raise

        # Extract polished text (fall back to original if missing)
        polished_title = improved.get('polished_title') or title
        polished_description = improved.get('polished_description') or description

        # Price recommendation is SEPARATE and optional
        raw_reco = improved.get('price_recommendation') or {}
        price_reco = None
        if isinstance(raw_reco, dict) and (raw_reco.get('recommended_price') is not None or raw_reco.get('range_low') is not None):
            price_reco = {
                'recommended_price': raw_reco.get('recommended_price'),
                'range_low': raw_reco.get('range_low'),
                'range_high': raw_reco.get('range_high'),
                'currency': raw_reco.get('currency') or 'ZAR',
                'why': raw_reco.get('why') or '',
                'confidence': raw_reco.get('confidence') or 'Medium',
                'local_context': raw_reco.get('local_context') or ''
            }

        return jsonify({
            'success': True,
            'polished_title': polished_title,
            'polished_description': polished_description,
            'price_recommendation': price_reco,
            # Always free now
            'is_free': True,
            'credits_used': 0,
            'remaining_credits': float(current_user.credit_balance or 0),
            'uses_today': 0,
            'remaining_free': 'unlimited'  # Polish is fully free
        })

    except Exception as e:
        return jsonify({'error': f'AI temporarily unavailable. ({str(e)})'}), 500


@listings_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = ListingForm()
    seed_categories()
    form.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    if not form.category.choices:
        form.category.choices = [(-1, "No categories yet — please run seed_categories.py")]

    # Polish with Grok is completely free (unlimited free subject only to hourly rate limit).
    # Pass a high number / 'unlimited' signal for UI.
    grok_remaining_free = 99
    has_unlimited_grok = current_user.has_active_unlimited_pass()

    if request.method == 'GET':
        form.contact_phone.data = getattr(current_user, 'phone', '') or getattr(current_user, 'contact_phone', '')
        form.contact_email.data = current_user.email

    if form.validate_on_submit():
        print(f"[LISTINGS CREATE] validate_on_submit()=True for user_id={current_user.id}")
        selected = form.contact_methods.data or []
        contact_phone = form.contact_phone.data if 'phone' in selected else None
        contact_email = form.contact_email.data if 'email' in selected else None
        contact_methods = ','.join(selected) if selected else 'dm,email,phone'

        photo_url = None
        photo_urls_list = []
        upload_dir = current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
        if form.photo.data:
            files = form.photo.data if isinstance(form.photo.data, (list, tuple)) else [form.photo.data]
            print(f"[LISTINGS CREATE] photo files received: {len(files) if files else 0}")
            for f in files:
                if f and getattr(f, 'filename', None) and allowed_file(f.filename):
                    filename = secure_filename(f.filename)
                    os.makedirs(upload_dir, exist_ok=True)
                    filepath = os.path.join(upload_dir, filename)
                    f.save(filepath)
                    resize_image_to_square(filepath)
                    url = f'/static/uploads/{filename}'
                    if photo_url is None:
                        photo_url = url
                    else:
                        photo_urls_list.append(url)
        photo_urls = ','.join(photo_urls_list) if photo_urls_list else None
        print(f"[LISTINGS CREATE] photo_url set: {photo_url}")

        price_type = form.price_type.data or 'fixed'

        # Defensive price cleaning: accept formatted values like "1,234.00" or "1 234,00"
        # in case client-side formatting slipped through. Keeps display nice while allowing save.
        def _safe_float(v):
            if v is None or v == '':
                return None
            if isinstance(v, (int, float)):
                return float(v)
            try:
                s = str(v).strip().replace(' ', '').replace('\xa0', '')
                # Robust handling for formatted input while keeping display (###,###.00)
                if '.' in s:
                    # Has dot → dot is decimal, strip any thousand commas
                    s = s.replace(',', '')
                elif ',' in s:
                    # No dot, has comma → check for decimal comma e.g. 1234,56 vs 1,234
                    parts = s.split(',')
                    if len(parts) == 2 and len(parts[1]) <= 2:
                        s = parts[0] + '.' + parts[1]
                    else:
                        s = s.replace(',', '')
                return float(s) if s else None
            except (ValueError, TypeError):
                return None

        if price_type == 'fixed':
            price = _safe_float(form.price.data) or 0.0
            min_price = None
            max_price = None
        else:
            price = 0.0
            min_price = _safe_float(form.min_price.data)
            max_price = _safe_float(form.max_price.data)

        rental_duration = form.rental_duration.data if form.post_type.data == 'rental' else None
        rental_duration_unit = form.rental_duration_unit.data if form.post_type.data == 'rental' else None

        is_business = current_user.is_business_account

        # ============================================================
        # v1.1 Credit System — Free Tier Logic (one free active 7-day listing)
        # Photos are COMPLETELY FREE (unlimited within max). No extra_photo_credits.
        # ============================================================
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        freshness = func.coalesce(Listing.last_reposted_at, Listing.created_at)
        active_count = db.session.query(Listing.id).filter(
            Listing.user_id == current_user.id,
            Listing.is_active == True,
            freshness >= seven_days_ago
        ).count()

        if not is_business:
            if active_count == 0:
                base_credits = 0
                listing_type = 'normal'
                is_free_slot = True
            else:
                base_credits = 1
                listing_type = 'normal'
                is_free_slot = False
        else:
            base_credits = 2
            listing_type = 'super'
            is_free_slot = False

        required_credits = base_credits   # photos always free
        had_active_before = active_count >= 1

        has_unlimited = current_user.has_active_unlimited_pass()
        if has_unlimited:
            required_credits = 0

        if required_credits > 0:
            current_balance = current_user.credit_balance or Decimal('0')
            req_dec = Decimal(str(required_credits))
            if current_balance < req_dec:
                if not is_business and had_active_before:
                    flash(
                        "You already have an active listing. "
                        "Let it expire or use 1 credit to post another one now.",
                        "warning"
                    )
                else:
                    who = "super/business" if is_business else "normal"
                    flash(f'Not enough credits. This {who} listing requires {required_credits} credit(s).', 'warning')
                return redirect(url_for('listings.create'))

            current_user.credit_balance = current_balance - req_dec
            txn = CreditTransaction(
                user_id=current_user.id,
                amount=-req_dec,
                transaction_type='listing',
                reference=f'listing_create_{datetime.utcnow().isoformat()}'
            )
            db.session.add(txn)
        else:
            txn = CreditTransaction(
                user_id=current_user.id,
                amount=Decimal('0'),
                transaction_type='free_active_slot' if not has_unlimited else 'unlimited_pass',
                reference=f'free_active_slot_{datetime.utcnow().isoformat()}' if not has_unlimited else f'unlimited_listing_{datetime.utcnow().isoformat()}'
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
            is_business_ad=current_user.is_business_account,
            is_active=True,
            listing_type=listing_type,
            rental_duration=rental_duration,
            rental_duration_unit=rental_duration_unit
        )

        try:
            print(f"[LISTINGS CREATE] committing listing title={listing.title!r} user_id={listing.user_id} photo={bool(listing.photo_url)}")
            db.session.add(listing)
            db.session.commit()
            print(f"[LISTINGS CREATE] COMMIT SUCCESS id={listing.id}")

            action = request.form.get('action') or request.form.get('submit_action')
            if required_credits == 0:
                if has_unlimited:
                    base_msg = 'Posted successfully with your Unlimited Pass (no credits used). All photos free.'
                else:
                    base_msg = 'Posted successfully as your free active listing. It will be live for 7 days. All photos free.'
            else:
                base_msg = f'Listing created successfully! {required_credits} credit(s) deducted. New balance: {current_user.credit_balance}. All photos free.'

            if action == 'create_new':
                flash(base_msg + ' Category, town & contacts kept for your next listing.', 'success')
                continue_form = ListingForm()
                seed_categories()
                continue_form.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
                continue_form.post_type.data = form.post_type.data
                continue_form.price_type.data = form.price_type.data
                continue_form.category.data = form.category.data
                continue_form.town.data = form.town.data
                continue_form.contact_methods.data = selected
                continue_form.contact_phone.data = contact_phone
                continue_form.contact_email.data = contact_email
                continue_form.allow_comments.data = form.allow_comments.data
                if form.post_type.data == 'rental':
                    continue_form.rental_duration_unit.data = form.rental_duration_unit.data
                    # Note: rental_duration cleared below

                # Clear ONLY title, description, pricing fields and photos as requested.
                # Everything else (category, town, contacts, post/price type, rental unit, allow_comments) stays.
                continue_form.title.data = ''
                continue_form.description.data = ''
                continue_form.price.data = None
                continue_form.min_price.data = None
                continue_form.max_price.data = None
                continue_form.rental_duration.data = None
                # Photos: fresh form render + client focus will handle; no photo data carried.

                return render_template('listings/create.html', form=continue_form, editing=False,
                                       grok_remaining_free=grok_remaining_free)
            else:
                flash(base_msg, 'success')
                return redirect(url_for('main.my_listings'))

        except Exception as e:
            db.session.rollback()
            print(f"[LISTINGS CREATE] COMMIT FAILED: {e}")
            flash(f'Error saving your listing: {str(e)}', 'danger')
            return redirect(url_for('listings.create'))

    # If POST reached here, validate failed - surface errors (fixes silent validation case)
    if request.method == 'POST' and form.errors:
        for field, errs in form.errors.items():
            for err in errs:
                flash(f'{field.replace("_", " ").title()}: {err}', 'danger')
    return render_template('listings/create.html', form=form,
                           grok_remaining_free=grok_remaining_free)


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

    if request.method == 'GET':
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
        if listing.contact_methods:
            form.contact_methods.data = [m.strip() for m in listing.contact_methods.split(',') if m.strip()]
        else:
            methods = ['dm']
            if listing.contact_email: methods.append('email')
            if listing.contact_phone: methods.append('phone')
            form.contact_methods.data = methods

    if form.validate_on_submit():
        selected = form.contact_methods.data or []
        contact_phone = form.contact_phone.data if 'phone' in selected else None
        contact_email = form.contact_email.data if 'email' in selected else None
        contact_methods = ','.join(selected) if selected else 'dm,email,phone'

        photo_url = listing.photo_url
        photo_urls = listing.photo_urls
        upload_dir = current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
        if form.photo.data:
            files = form.photo.data if isinstance(form.photo.data, (list, tuple)) else [form.photo.data]
            new_photos = []
            for f in files:
                if f and getattr(f, 'filename', None) and allowed_file(f.filename):
                    filename = secure_filename(f.filename)
                    os.makedirs(upload_dir, exist_ok=True)
                    filepath = os.path.join(upload_dir, filename)
                    f.save(filepath)
                    resize_image_to_square(filepath)
                    new_photos.append(f'/static/uploads/{filename}')
            if new_photos:
                photo_url = new_photos[0]
                photo_urls = ','.join(new_photos[1:]) if len(new_photos) > 1 else None

        price_type = form.price_type.data or 'fixed'

        # Defensive price cleaning: accept formatted values like "1,234.00" or "1 234,00"
        # in case client-side formatting slipped through. Keeps display nice while allowing save.
        def _safe_float(v):
            if v is None or v == '':
                return None
            if isinstance(v, (int, float)):
                return float(v)
            try:
                s = str(v).strip().replace(' ', '').replace('\xa0', '')
                # Robust handling for formatted input while keeping display (###,###.00)
                if '.' in s:
                    # Has dot → dot is decimal, strip any thousand commas
                    s = s.replace(',', '')
                elif ',' in s:
                    # No dot, has comma → check for decimal comma e.g. 1234,56 vs 1,234
                    parts = s.split(',')
                    if len(parts) == 2 and len(parts[1]) <= 2:
                        s = parts[0] + '.' + parts[1]
                    else:
                        s = s.replace(',', '')
                return float(s) if s else None
            except (ValueError, TypeError):
                return None

        if price_type == 'fixed':
            price = _safe_float(form.price.data) or 0.0
            min_price = None
            max_price = None
        else:
            price = 0.0
            min_price = _safe_float(form.min_price.data)
            max_price = _safe_float(form.max_price.data)

        rental_duration = form.rental_duration.data if form.post_type.data == 'rental' else None
        rental_duration_unit = form.rental_duration_unit.data if form.post_type.data == 'rental' else None

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
            return render_template('listings/create.html', form=form, listing=listing, editing=True,
                                   grok_remaining_free=99)

    return render_template('listings/create.html', form=form, listing=listing, editing=True, grok_remaining_free=99)


@listings_bp.route('/quick-create', methods=['GET', 'POST'])
@login_required
def quick_create():
    if not current_user.is_business_account:
        flash('Quick-create is only available to Business accounts.', 'warning')
        return redirect(url_for('listings.create'))

    form = ListingForm()
    seed_categories()
    form.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]

    if request.method == 'GET':
        form.contact_phone.data = current_user.phone
        form.contact_email.data = current_user.email or ''

    if form.validate_on_submit():
        selected = form.contact_methods.data or []
        contact_phone = form.contact_phone.data if 'phone' in selected else None
        contact_email = form.contact_email.data if 'email' in selected else None
        contact_methods = ','.join(selected) if selected else 'dm,email,phone'

        photo_url = None
        photo_urls_list = []
        upload_dir = current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
        if form.photo.data:
            files = form.photo.data if isinstance(form.photo.data, (list, tuple)) else [form.photo.data]
            for f in files:
                if f and getattr(f, 'filename', None) and allowed_file(f.filename):
                    filename = secure_filename(f.filename)
                    os.makedirs(upload_dir, exist_ok=True)
                    filepath = os.path.join(upload_dir, filename)
                    f.save(filepath)
                    resize_image_to_square(filepath)
                    url = f'/static/uploads/{filename}'
                    if photo_url is None:
                        photo_url = url
                    else:
                        photo_urls_list.append(url)
        photo_urls = ','.join(photo_urls_list) if photo_urls_list else None

        price_type = form.price_type.data or 'fixed'

        # Defensive price cleaning: accept formatted values like "1,234.00" or "1 234,00"
        # in case client-side formatting slipped through. Keeps display nice while allowing save.
        def _safe_float(v):
            if v is None or v == '':
                return None
            if isinstance(v, (int, float)):
                return float(v)
            try:
                s = str(v).strip().replace(' ', '').replace('\xa0', '')
                # Robust handling for formatted input while keeping display (###,###.00)
                if '.' in s:
                    # Has dot → dot is decimal, strip any thousand commas
                    s = s.replace(',', '')
                elif ',' in s:
                    # No dot, has comma → check for decimal comma e.g. 1234,56 vs 1,234
                    parts = s.split(',')
                    if len(parts) == 2 and len(parts[1]) <= 2:
                        s = parts[0] + '.' + parts[1]
                    else:
                        s = s.replace(',', '')
                return float(s) if s else None
            except (ValueError, TypeError):
                return None

        if price_type == 'fixed':
            price = _safe_float(form.price.data) or 0.0
            min_price = None
            max_price = None
        else:
            price = 0.0
            min_price = _safe_float(form.min_price.data)
            max_price = _safe_float(form.max_price.data)

        rental_duration = form.rental_duration.data if form.post_type.data == 'rental' else None
        rental_duration_unit = form.rental_duration_unit.data if form.post_type.data == 'rental' else None

        required_credits = 2
        # Photos are completely free - no extra charge
        total_required = required_credits
        total_dec = Decimal(str(total_required))
        curr_bal = current_user.credit_balance or Decimal('0')

        has_unlimited = current_user.has_active_unlimited_pass()
        if has_unlimited:
            total_required = 0
            total_dec = Decimal('0')

        if total_required > 0 and curr_bal < total_dec:
            flash(f'Not enough credits. Quick-create requires {total_required} credits.', 'warning')
            return render_template('listings/quick_create.html', form=form, grok_remaining_free=99)

        if total_required > 0:
            current_user.credit_balance = curr_bal - total_dec
        txn = CreditTransaction(
            user_id=current_user.id,
            amount=-total_dec if total_required > 0 else Decimal('0'),
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
            is_active=True,
            listing_type='super',
            rental_duration=rental_duration,
            rental_duration_unit=rental_duration_unit
        )

        try:
            db.session.add(listing)
            db.session.commit()
            if has_unlimited:
                flash('Listing saved with your Unlimited Pass (no credits used)! All photos free.', 'success')
            else:
                flash(f'Listing saved! {total_required} credits deducted. New balance: {current_user.credit_balance}. All photos free.', 'success')
            return redirect(url_for('listings.quick_create'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving your listing: {str(e)}', 'danger')
            return render_template('listings/quick_create.html', form=form, grok_remaining_free=99)

    return render_template('listings/quick_create.html', form=form, grok_remaining_free=99)


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


# ============================================================
# Repost (for EXPIRED listings only) — v1.1 spec
# Costs 1 credit, sets last_reposted_at (refreshes 7-day window), created_at untouched.
# Button only shown on expired cards in my_listings.
# ============================================================
@listings_bp.route('/listing/<int:listing_id>/repost', methods=['POST'])
@login_required
def repost_listing(listing_id):
    listing = Listing.query.get_or_404(listing_id)

    if listing.user_id != current_user.id:
        flash("You can only repost your own listings.", "danger")
        return redirect(url_for('main.my_listings'))

    if not listing.is_expired:
        flash("This listing is still active.", "info")
        return redirect(url_for('main.my_listings'))

    has_unlimited = current_user.has_active_unlimited_pass()
    if not has_unlimited and (current_user.credit_balance or Decimal('0')) < Decimal('1'):
        flash("You need 1 credit to repost.", "warning")
        return redirect(url_for('main.my_listings'))

    try:
        if not has_unlimited:
            current_user.credit_balance = (current_user.credit_balance or Decimal('0')) - Decimal('1')

        now = datetime.utcnow()
        listing.last_reposted_at = now
        listing.refreshed_at = now   # v1.2 spec: update refreshed_at on repost
        # Repost refreshes visibility but does not force promoted badge (boost does)
        # listing.is_promoted remains as-is

        tx = CreditTransaction(
            user_id=current_user.id,
            amount=Decimal('0') if has_unlimited else Decimal('-1'),
            transaction_type='repost',
            reference=f'repost_listing_{listing.id}'
        )
        db.session.add(tx)
        db.session.commit()

        flash("Listing reposted! It is now visible on the homepage again.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error reposting listing: {str(e)}", "danger")

    return redirect(url_for('main.my_listings'))


# ============================================================
# Share-to-Earn (Share Buttons with Credit Rewards)
# +0.5 credits per share (WA/FB/X). Daily cap 3 credits = max 6 shares/day (SAST midnight reset).
# Per-listing dedup to prevent rapid spam. Supports AJAX JSON + legacy.
# ============================================================
@listings_bp.route('/listing/<int:listing_id>/share', methods=['POST'])
@login_required
def share_listing(listing_id):
    # Robust AJAX detection
    accept = (request.headers.get('Accept') or '').lower()
    is_ajax = bool(
        request.headers.get('HX-Request') or
        request.is_json or
        'application/json' in accept or
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )

    SHARE_REWARD = Decimal('0.5')
    DAILY_CAP = Decimal('3.0')
    MAX_SHARES = 6

    today = current_user.get_sast_today() if hasattr(current_user, 'get_sast_today') else date.today()
    start_of_today = datetime.combine(today, datetime.min.time())

    # Compute authoritative daily share count DIRECTLY from the transaction log.
    # This is robust: 6 shares = 6 'share_reward' tx rows today (resets naturally at midnight SAST
    # because we filter by created_at >= start_of_today). No reliance on the denorm counter for decisions.
    # The user.shares_rewarded_today / last_share... are still updated for compatibility/display but
    # the cap/earned use the real tx history so counters can't get out of sync or block early.
    shares_today = CreditTransaction.query.filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.transaction_type == 'share_reward',
        CreditTransaction.created_at >= start_of_today
    ).count()

    current_balance = float(current_user.credits or 0)

    # Daily cap check (based on actual rewards recorded today)
    if shares_today >= MAX_SHARES:
        msg = "Daily share limit reached (3 credits max). Thanks for spreading the word in the Karoo!"
        if is_ajax:
            earned_today = float(DAILY_CAP)
            return jsonify({
                'success': False, 'awarded': 0, 'message': msg,
                'limit_reached': True, 'new_balance': current_balance,
                'shares_today': shares_today,
                'earned_today': earned_today, 'cap': float(DAILY_CAP), 'reached_cap': True
            })
        flash(msg, "info")
        return redirect(request.referrer or url_for('main.my_listings'))

    # Per-listing dedup for today (still uses tx log)
    already = CreditTransaction.query.filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.transaction_type == 'share_reward',
        CreditTransaction.reference == f'share_listing_{listing_id}',
        CreditTransaction.created_at >= start_of_today
    ).first()

    if already:
        msg = "You've already earned credit for sharing this listing today."
        if is_ajax:
            earned_today = min(float(DAILY_CAP), float(shares_today * 0.5))
            return jsonify({
                'success': True, 'awarded': 0, 'message': msg, 'duplicate': True,
                'new_balance': current_balance, 'shares_today': shares_today,
                'earned_today': earned_today, 'cap': float(DAILY_CAP), 'reached_cap': earned_today >= float(DAILY_CAP)
            })
        flash(msg, "info")
        return redirect(request.referrer or url_for('main.index'))

    # Award the credit
    try:
        current_user.credits = (current_user.credits or Decimal('0')) + SHARE_REWARD

        # Update denorm counter from authoritative count (for any other UI that reads the user column)
        new_shares_count = shares_today + 1
        current_user.shares_rewarded_today = new_shares_count
        current_user.last_share_reward_date = today

        db.session.add(CreditTransaction(
            user_id=current_user.id,
            amount=SHARE_REWARD,
            transaction_type='share_reward',
            reference=f'share_listing_{listing_id}'
        ))
        db.session.commit()

        earned_today = float(new_shares_count * 0.5)
        reached_cap = earned_today >= float(DAILY_CAP)

        if reached_cap:
            cap_str = f"{float(DAILY_CAP):g}"
            msg = f"You have earned {cap_str}/{cap_str} credits for today! You will be eligible to earn credits again after midnight."
        else:
            # e.g. "Congrats you have earned 0.5 of 3 credits today"
            earned_str = f"{earned_today:g}"
            cap_str = f"{float(DAILY_CAP):g}"
            msg = f"Congrats you have earned {earned_str} of {cap_str} credits today"

        if is_ajax:
            return jsonify({
                'success': True,
                'awarded': float(SHARE_REWARD),
                'message': msg,
                'new_balance': float(current_user.credits or 0),
                'shares_today': new_shares_count,
                'earned_today': earned_today,
                'cap': float(DAILY_CAP),
                'reached_cap': reached_cap
            })

        flash(msg, "success")
    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'awarded': 0, 'message': 'Could not award credit right now.', 'new_balance': float(current_user.credits or 0)})
        flash(f"Could not award share credit: {str(e)}", "danger")

    return redirect(request.referrer or url_for('main.my_listings'))


# ============================================================
# Mark as Sold — frees active slot immediately, hides from public/search
# Sets is_active=False (consistent with free slot counting logic)
# ============================================================
@listings_bp.route('/listing/<int:listing_id>/mark-sold', methods=['POST'])
@login_required
def mark_sold(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    if listing.user_id != current_user.id:
        flash('You can only manage your own listings.', 'danger')
        return redirect(url_for('main.my_listings'))

    if not listing.is_active:
        flash('This listing is already inactive.', 'info')
        return redirect(url_for('main.my_listings'))

    try:
        listing.is_active = False
        db.session.commit()
        flash('Listing marked as sold. Your slot is now free.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error marking as sold: {str(e)}', 'danger')

    return redirect(url_for('main.my_listings'))


@listings_bp.route('/listing/<int:listing_id>')
def detail(listing_id):
    # Load with user eagerly for seller info in SEO + templates
    listing = Listing.query.options(joinedload(Listing.user)).get_or_404(listing_id)

    # Increment views safely (using the correct model attribute)
    current_views = getattr(listing, 'views', 0) or 0
    listing.views = current_views + 1
    db.session.commit()

    # Message form for DM modal
    message_form = None
    cm = (listing.contact_methods or '').strip()
    methods = [m.strip() for m in cm.split(',') if m.strip()] if cm else ['dm', 'email', 'phone']
    if 'dm' in methods and current_user.is_authenticated and current_user.id != listing.user_id:
        message_form = MessageForm()
        message_form.receiver_id.data = listing.user_id
        message_form.listing_id.data = listing.id

    # SEO Enhancement (spec v1.0): server-rendered title, meta, OG-ready, full Product+Offer JSON-LD
    page_title = f"{listing.title} in {listing.location}, Klein Karoo | VolstruisGids"

    # Meta description (refined): respect user's description, keep it natural.
    # Always include town + Klein Karoo. Target ~155 chars max.
    raw_desc = (listing.description or '').strip().replace('\r', ' ').replace('\n', ' ')
    raw_desc = ' '.join(raw_desc.split())  # collapse multiple spaces
    if len(raw_desc) > 20:
        # Take a generous chunk and cut cleanly at sentence or word boundary
        chunk = raw_desc[:128]
        if '. ' in chunk:
            short = chunk.rsplit('. ', 1)[0] + '.'
        else:
            short = chunk.rsplit(' ', 1)[0].rstrip('.,;: ')
        meta_description = f"{short} Available in {listing.location}, Klein Karoo on VolstruisGids."
    else:
        price_part = ""
        if listing.price and listing.price > 0:
            price_part = f" for R{int(listing.price):,}"
        elif listing.price_type == 'range' and listing.min_price and listing.max_price:
            price_part = f" (R{int(listing.min_price):,}–R{int(listing.max_price):,})"
        meta_description = f"Buy {listing.title}{price_part} in {listing.location}, Klein Karoo. Safe local classifieds on VolstruisGids. Contact the seller."

    if len(meta_description) > 158:
        meta_description = meta_description[:155].rsplit(' ', 1)[0] + "..."

    # === Dynamic keywords meta (SEO polish for per-listing relevance) ===
    # Builds a targeted, deduplicated list: title + location + post_type + core site terms
    kw_parts = [listing.title, listing.location]
    if listing.post_type:
        kw_parts.append(listing.post_type)
    kw_parts.extend(['Klein Karoo', 'VolstruisGids', 'local classifieds'])

    if listing.post_type in ('services', 'service'):
        kw_parts.append('services')

    # Deduplicate while preserving order (case-insensitive)
    seen = set()
    unique_kw = []
    for p in kw_parts:
        p_clean = p.strip().lower()
        if p_clean and p_clean not in seen:
            seen.add(p_clean)
            unique_kw.append(p)

    meta_keywords = ', '.join(unique_kw) + ', buy sell local, Western Cape ads, free listings'

    # Absolute URLs for images (OG + schema)
    def _abs_url(p):
        if not p:
            return None
        if p.startswith(('http://', 'https://')):
            return p
        root = request.url_root.rstrip('/')
        return root + (p if p.startswith('/') else '/' + p)

    primary_photo = listing.photo_url
    if not primary_photo and listing.photo_urls:
        first = [x.strip() for x in listing.photo_urls.split(',') if x.strip()]
        if first:
            primary_photo = first[0]
    og_image_url = _abs_url(primary_photo) if primary_photo else None

    # Always provide an image for Product schema and OG (fallback to default)
    if not og_image_url:
        default_path = url_for('static', filename='img/default-listing.jpg')
        og_image_url = request.url_root.rstrip('/') + default_path

    # Build list of images for schema (helps Product rich results)
    images = []
    if listing.photo_url:
        images.append(_abs_url(listing.photo_url))
    if listing.photo_urls:
        for p in listing.photo_urls.split(','):
            p = p.strip()
            if p:
                images.append(_abs_url(p))
    if not images:
        images = [og_image_url]

    # Build JSON-LD Product + Offer (location-aware, seller-aware)
    if listing.user:
        if listing.is_business_ad and getattr(listing.user, 'business_name', None):
            seller_name = listing.user.business_name
        else:
            seller_name = listing.user.username or 'Local Seller'
    else:
        seller_name = 'Local Seller in Klein Karoo'
    seller_type = "Organization" if listing.is_business_ad else "Person"

    # Clean description for schema
    schema_desc_source = listing.description or meta_description
    schema_desc = ' '.join(schema_desc_source.replace('\r', ' ').replace('\n', ' ').split()).strip()[:500]

    structured_data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": listing.title,
        "sku": f"VG{listing.id}",
        "description": schema_desc,
        "url": request.url,
        "brand": {
            "@type": "Brand",
            "name": "VolstruisGids"
        },
        "areaServed": {
            "@type": "City",
            "name": listing.location
        },
        "offers": {
            "@type": "Offer",
            "url": request.url,
            "priceCurrency": "ZAR",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/UsedCondition",
            "availableAtOrFrom": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": listing.location,
                    "addressRegion": "Western Cape",
                    "addressCountry": "ZA"
                }
            },
            "shippingDetails": {
                "@type": "OfferShippingDetails",
                "shippingRate": {
                    "@type": "MonetaryAmount",
                    "value": "0",
                    "currency": "ZAR"
                },
                "shippingDestination": {
                    "@type": "DefinedRegion",
                    "addressCountry": "ZA"
                },
                "deliveryMethod": "https://schema.org/OnSitePickup",
                "deliveryTime": {
                    "@type": "ShippingDeliveryTime",
                    "handlingTime": {
                        "@type": "QuantitativeValue",
                        "minValue": 0,
                        "maxValue": 1,
                        "unitCode": "DAY"
                    }
                }
            },
            "hasMerchantReturnPolicy": {
                "@type": "MerchantReturnPolicy",
                "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
                "merchantReturnDays": 0,
                "returnFees": "https://schema.org/FreeReturn",
                "returnMethod": "https://schema.org/ReturnByMail",
                "applicableCountry": "ZA"
            },
            "seller": {
                "@type": seller_type,
                "name": seller_name,
                "url": "https://www.volstruisgids.co.za"
            }
        }
    }

    # Only include price when we have a positive value. Use string for better parser compatibility.
    price_val = None
    if listing.price and listing.price > 0:
        price_val = str(listing.price)
    elif listing.price_type == 'range' and listing.min_price is not None and listing.min_price > 0:
        price_val = str(listing.min_price)

    if price_val is not None:
        structured_data["offers"]["price"] = price_val

    # Help reduce non-critical issues in Google Rich Results for offers
    structured_data["offers"]["priceValidUntil"] = (datetime.utcnow() + timedelta(days=30)).date().isoformat()

    if images:
        structured_data["image"] = images
    elif og_image_url:
        structured_data["image"] = [og_image_url]

    return render_template('listings/detail.html',
                           listing=listing,
                           message_form=message_form,
                           page_title=page_title,
                           meta_description=meta_description,
                           meta_keywords=meta_keywords,          # NEW
                           structured_data=structured_data,
                           og_image_url=og_image_url)


@listings_bp.route('/category/<string:category_name>')
def by_category(category_name):
    category = Category.query.filter_by(name=category_name).first_or_404()
    # Apply 7-day freshness filter (public category listings)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    freshness = db.func.coalesce(Listing.last_reposted_at, Listing.created_at)
    listings = (Listing.query
        .options(joinedload(Listing.user))
        .filter(
            Listing.category_id == category.id,
            Listing.is_active == True,
            freshness >= seven_days_ago
        )
        .order_by(Listing.created_at.desc())
        .all())
    return render_template('listings/category.html', category=category, listings=listings)