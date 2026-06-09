# app/blueprints/main/routes.py
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from app.models.category import Category
from app.models.credit_transaction import CreditTransaction
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from . import main_bp
import os
from werkzeug.utils import secure_filename
from PIL import Image
import requests
from datetime import datetime, date
from flask import send_from_directory

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


# ============================================================
# Daily Free Credit Refresh (+2 credits once per day)
# ============================================================
def ensure_daily_free_credits(user):
    """
    Automatically gives the user +2 free credits once per calendar day.
    Safe to call multiple times — it only gives credits once per day.
    """
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())

    # Check if user already received daily free credits today
    already_received = CreditTransaction.query.filter(
        CreditTransaction.user_id == user.id,
        CreditTransaction.transaction_type == 'daily_free',
        CreditTransaction.created_at >= start_of_day
    ).first()

    if already_received:
        return False

    try:
        user.credit_balance += 2

        tx = CreditTransaction(
            user_id=user.id,
            amount=2,
            transaction_type='daily_free',
            reference=f'daily_free_{today.isoformat()}'
        )
        db.session.add(tx)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error giving daily free credits: {e}")
        return False


@main_bp.route('/')
def index():
    return render_template('main/index.html')


@main_bp.route('/api/listings')
def api_listings():
    """AJAX endpoint for homepage listings feed with working filters."""
    query = request.args.get('q', '').strip()
    post_type = request.args.get('post_type', '').strip()
    town = request.args.get('town', '').strip()
    user_id = request.args.get('user_id')
    category = request.args.get('category', '').strip()
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
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

    if user_id:
        try:
            listings_query = listings_query.filter(Listing.user_id == int(user_id))
        except ValueError:
            pass

    if category:
        try:
            cat = Category.query.filter_by(name=category).first()
            if cat:
                listings_query = listings_query.filter(Listing.category_id == cat.id)
        except Exception:
            pass

    # === BOOST / REPROMOTE LOGIC ===
    # Promoted listings first, then most recent last_reposted_at (falls back to created_at)
    # This makes a fresh boost bubble the listing back to the top of the grid for ~7 days visibility.
    freshness = func.coalesce(Listing.last_reposted_at, Listing.created_at)
    listings = listings_query.order_by(
        Listing.is_promoted.desc(),
        freshness.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    listings_data = [{
        'id': l.id,
        'title': l.title,
        'description': l.description[:100] + '...' if l.description else '',
        'price': l.price if l.price and l.price > 0 else None,
        'min_price': l.min_price,
        'max_price': l.max_price,
        'location': l.location,
        'post_type': l.post_type,
        'photo_url': l.photo_url,
        'photo_urls': l.photo_urls,
        'detail_url': url_for('listings.detail', listing_id=l.id),
        'is_business_ad': l.is_business_ad,
        'business_name': l.user.business_name if l.is_business_ad and l.user and l.user.business_name else None,
        'business_logo': l.user.profile_pic if l.is_business_ad and l.user and l.user.profile_pic else None,
        'username': (l.user.username or 'unknown').lstrip('@') if l.user else 'unknown',
        'user_id': l.user_id,
        'ad_type': l.post_type,
        'category': l.category.name if l.category else '',
        'rental_duration': l.rental_duration,
        'rental_duration_unit': l.rental_duration_unit,
        'is_promoted': l.is_promoted,
        'last_reposted_at': l.last_reposted_at.isoformat() if l.last_reposted_at else None,
        'listing_type': l.listing_type
    } for l in listings.items]

    return jsonify({
        'listings': listings_data,
        'has_more': listings.has_next,
        'next_page': page + 1 if listings.has_next else None
    })


@main_bp.route('/api/categories')
def api_categories():
    """Return categories with active listing counts."""
    query = request.args.get('q', '').strip()
    post_type = request.args.get('post_type', '').strip()
    town = request.args.get('town', '').strip()
    user_id = request.args.get('user_id')

    cat_query = db.session.query(
        Category.name, func.count(Listing.id).label('count')
    ).join(Listing, Listing.category_id == Category.id
    ).filter(Listing.is_active == True)

    if query:
        cat_query = cat_query.filter(
            (Listing.title.ilike(f'%{query}%')) |
            (Listing.description.ilike(f'%{query}%'))
        )

    if post_type:
        cat_query = cat_query.filter(Listing.post_type == post_type)

    if town:
        cat_query = cat_query.filter(Listing.location == town)

    if user_id:
        try:
            cat_query = cat_query.filter(Listing.user_id == int(user_id))
        except ValueError:
            pass

    counts = cat_query.group_by(Category.name).order_by(func.count(Listing.id).desc()).all()

    return jsonify([
        {'name': name, 'count': count} for name, count in counts
    ])


@main_bp.route('/my-listings')
@login_required
def my_listings():
    # Also apply freshness sort so your own boosted listings stay prominent
    freshness = func.coalesce(Listing.last_reposted_at, Listing.created_at)
    listings = Listing.query.filter_by(user_id=current_user.id)\
        .order_by(Listing.is_promoted.desc(), freshness.desc()).all()
    return render_template('main/my_listings.html', listings=listings)


@main_bp.route('/robots.txt')
def robots_txt():
    return send_from_directory(
        os.path.join(current_app.root_path, 'static'),
        'robots.txt',
        mimetype='text/plain'
    )


@main_bp.route('/terms')
def terms():
    return render_template('main/terms.html')


@main_bp.route('/privacy')
def privacy():
    return render_template('main/privacy.html')


@main_bp.route('/guidelines')
def guidelines():
    return render_template('main/guidelines.html')


@main_bp.route('/my-listings/delete/<int:listing_id>', methods=['POST'])
@login_required
def delete_listing(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    if listing.user_id != current_user.id:
        flash('You can only delete your own listings.', 'danger')
        return redirect(url_for('main.my_listings'))
    db.session.delete(listing)
    db.session.commit()
    flash('Listing deleted successfully', 'success')
    return redirect(url_for('main.my_listings'))


# ============================================================
# Grok AI Chat endpoint (Daily credits + 2 free queries per day)
# ============================================================
@main_bp.route('/api/ai/ask', methods=['POST'])
@login_required
def ai_ask_listing():
    # Ensure user receives their daily +2 free credits
    ensure_daily_free_credits(current_user)

    data = request.get_json() or {}
    listing_id = data.get('listing_id')
    question = (data.get('question') or '').strip()

    if not listing_id or not question:
        return jsonify({'error': 'Missing listing_id or question'}), 400

    listing = Listing.query.get_or_404(listing_id)

    # Count how many AI queries the user has made today
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())

    ai_uses_today = CreditTransaction.query.filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.transaction_type == 'ai_query',
        CreditTransaction.created_at >= start_of_day
    ).count()

    is_free = ai_uses_today < 2

    if not is_free:
        if current_user.credit_balance < 1:
            return jsonify({
                'error': 'You have used your 2 free AI questions today. Please purchase more credits to continue.'
            }), 402
        current_user.credit_balance -= 1

    # Record the transaction
    tx = CreditTransaction(
        user_id=current_user.id,
        amount=0 if is_free else -1,
        transaction_type='ai_query',
        reference=f'listing_{listing_id}'
    )
    db.session.add(tx)
    db.session.commit()

    # === Build context for Grok ===
    price_str = ''
    if listing.price_type == 'range' and listing.min_price and listing.max_price:
        price_str = f"R{listing.min_price} – R{listing.max_price}"
    elif listing.price:
        price_str = f"R{listing.price}"

    system_prompt = f"""You are a helpful, practical assistant for Volstruis Gids — a local classifieds platform in the Klein Karoo, South Africa.
The user is asking a question about this specific listing. Be concise, friendly, and realistic. Use South African context where helpful.

Listing details:
- Title: {listing.title}
- Description: {listing.description or 'No description provided'}
- Price: {price_str or 'Not specified'}
- Area: {listing.area or listing.location or 'Klein Karoo'}
- Category / Type: {listing.post_type or 'General'}
- Posted: {listing.created_at.strftime('%d %B %Y') if listing.created_at else 'recently'}

Answer the user's question directly about this listing. If the question is unrelated, gently steer back to the listing. Keep answers short and actionable."""

    try:
        api_key = current_app.config.get('GROK_API_KEY')
        if not api_key:
            return jsonify({'error': 'AI service is not configured. Please contact support.'}), 500

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": current_app.config.get('GROK_MODEL', 'grok-3'),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            "max_tokens": 400,
            "temperature": 0.6
        }

        resp = requests.post(
            current_app.config.get('GROK_API_URL'),
            json=payload,
            headers=headers,
            timeout=25
        )
        resp.raise_for_status()
        answer = resp.json()['choices'][0]['message']['content'].strip()

        return jsonify({
            'answer': answer,
            'is_free': is_free,
            'remaining_free_today': max(0, 2 - (ai_uses_today + 1))
        })

    except requests.exceptions.RequestException as e:
        db.session.rollback()
        return jsonify({'error': 'Sorry, the AI service is temporarily unavailable. Please try again in a moment.'}), 503
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Unexpected error processing your question.'}), 500
    