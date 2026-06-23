# app/blueprints/main/routes.py
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, abort
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from app.models.user import User
from app.models.category import Category
from app.models.credit_transaction import CreditTransaction
from app.models.site_stat import SiteStat
from app.models.user_ai_usage import UserAIUsage
from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_
from . import main_bp

# Press releases data (easy to maintain)
try:
    from app.press_releases import PRESS_RELEASES
except Exception:
    PRESS_RELEASES = []

# Public pricing data for how-it-works page (and elsewhere)
try:
    from app.blueprints.payments.routes import UNLIMITED_PASSES
except Exception:
    UNLIMITED_PASSES = {
        "pass_30": {"days": 30, "price_zar": 299, "name": "30-Day Unlimited Pass"},
        "pass_60": {"days": 60, "price_zar": 499, "name": "60-Day Unlimited Pass"},
        "pass_90": {"days": 90, "price_zar": 699, "name": "90-Day Unlimited Pass"},
    }
import os
from werkzeug.utils import secure_filename
from PIL import Image
import requests
from datetime import datetime, date, timedelta
from decimal import Decimal
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
        user.credit_balance = (user.credit_balance or Decimal('0')) + Decimal('2')

        tx = CreditTransaction(
            user_id=user.id,
            amount=Decimal('2'),
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


# ============================================================
# Site-wide view counter — monthly aware for marketing messaging
# "Your ad could have been viewed X times this month!"
# ============================================================
def record_site_view():
    """Increment lifetime total + current month counter.
    Returns the *current month's* view count after increment.
    """
    try:
        now = datetime.utcnow()
        month_key = f"views_{now.year:04d}-{now.month:02d}"
        SiteStat.increment('total_views', 1)
        monthly = SiteStat.increment(month_key, 1)
        return monthly
    except Exception:
        return 0


def get_current_month_views():
    """Return how many views recorded for the current calendar month (no side effects)."""
    try:
        now = datetime.utcnow()
        month_key = f"views_{now.year:04d}-{now.month:02d}"
        return SiteStat.get_value(month_key, 0)
    except Exception:
        return 0


def get_total_site_views():
    """Lifetime total views (kept for reference)."""
    try:
        return SiteStat.get_value('total_views', 0)
    except Exception:
        return 0


@main_bp.route('/')
def index():
    # Record a visit (increments this month's counter + lifetime)
    monthly_views = record_site_view()

    # Credits for homepage top section (spec: pass explicit value; None for anonymous)
    user_credits = None
    if current_user.is_authenticated:
        if current_user.has_active_unlimited_pass():
            user_credits = 'unlimited'
        else:
            bal = current_user.credits
            if bal is None:
                bal = current_user.credit_balance
            try:
                user_credits = float(bal) if bal is not None else 0.0
            except (TypeError, ValueError):
                user_credits = 0.0

    return render_template('main/index.html', monthly_views=monthly_views, user_credits=user_credits)


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

    # Base freshness filter (7 days) — ALWAYS first for public homepage (per spec)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    freshness = func.coalesce(Listing.last_reposted_at, Listing.created_at)
    listings_query = Listing.query.options(joinedload(Listing.user)).filter(
        Listing.is_active == True,
        freshness >= seven_days_ago
    )

    if query:
        # Robust case-insensitive partial match on title OR description (per bugfix spec)
        like = f'%{query}%'
        listings_query = listings_query.filter(
            or_(Listing.title.ilike(like), Listing.description.ilike(like))
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
        'listing_type': l.listing_type,
        # === FIX: Always include profile_pic so owner pictures show on every listing ===
        'profile_pic': l.user.profile_pic if l.user else None
    } for l in listings.items]

    # === STOREFRONT CONTEXT (for business-only storefront enforcement) ===
    storefront_owner = None
    if user_id:
        try:
            target = User.query.get(int(user_id))
            if target:
                storefront_owner = {
                    'user_id': target.id,
                    'username': (target.username or '').lstrip('@'),
                    'business_name': target.business_name,
                    'is_business_account': bool(target.is_business_account),
                    'storefront_enabled': bool(target.storefront_enabled),
                    'profile_pic': target.profile_pic,
                }
        except Exception:
            pass

    return jsonify({
        'listings': listings_data,
        'has_more': listings.has_next,
        'next_page': page + 1 if listings.has_next else None,
        'storefront_owner': storefront_owner,
        'monthly_views': get_current_month_views()
    })


@main_bp.route('/api/categories')
def api_categories():
    """Return categories with active listing counts."""
    query = request.args.get('q', '').strip()
    post_type = request.args.get('post_type', '').strip()
    town = request.args.get('town', '').strip()
    user_id = request.args.get('user_id')

    # Apply same 7-day freshness base filter for accurate category counts on public
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    freshness = func.coalesce(Listing.last_reposted_at, Listing.created_at)
    cat_query = db.session.query(
        Category.name, func.count(Listing.id).label('count')
    ).join(Listing, Listing.category_id == Category.id
    ).filter(Listing.is_active == True, freshness >= seven_days_ago)

    if query:
        # Robust case-insensitive partial match on title OR description (per bugfix spec)
        like = f'%{query}%'
        cat_query = cat_query.filter(
            or_(Listing.title.ilike(like), Listing.description.ilike(like))
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


# ============================================================
# BUSINESS DIRECTORY API + VIEW (Business Directory + Homepage Toggle feature)
# ============================================================
@main_bp.route('/api/businesses')
def api_businesses():
    """Return business accounts for the directory view.
    Supports search, town, and business category filters.
    Only returns accounts that have upgraded to business.
    Includes active (recent) listing count.
    """
    q = (request.args.get('q', '') or '').strip()
    town = (request.args.get('town', '') or '').strip()
    category = (request.args.get('category', '') or '').strip()  # maps to business_type
    verified_only = request.args.get('verified_only', 'false').lower() == 'true'

    query = User.query.filter(
        db.or_(
            User.is_business == True,
            User.account_type == 'business',
            User.business_name.isnot(None)  # catch legacy / profile-upgraded accounts
        )
    )

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                User.business_name.ilike(like),
                User.username.ilike(like),
                User.bio.ilike(like)
            )
        )

    if town:
        query = query.filter(User.location == town)

    if category:
        query = query.filter(User.business_type == category)

    if verified_only:
        query = query.filter(User.business_verified == True)

    # Order: verified first, then by name
    businesses = query.order_by(
        User.business_verified.desc(),
        User.business_name.asc().nullslast(),
        User.username.asc()
    ).limit(60).all()   # reasonable cap for MVP

    results = []
    for b in businesses:
        # Count active listings (use same 7-day freshness as homepage for "active")
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        freshness = func.coalesce(Listing.last_reposted_at, Listing.created_at)
        active_count = Listing.query.filter(
            Listing.user_id == b.id,
            Listing.is_active == True,
            freshness >= seven_days_ago
        ).count()

        # Prefer business_phone for WhatsApp, fall back to personal phone
        wa_phone = getattr(b, 'business_phone', None) or getattr(b, 'phone', None)
        contact_email = getattr(b, 'email', None)

        results.append({
            'id': b.id,
            'username': (b.username or '').lstrip('@'),
            'business_name': b.business_name or b.username,
            'bio': (b.bio or '')[:140],
            'location': b.location,
            'profile_pic': b.profile_pic,
            'business_type': b.business_type,
            'business_verified': bool(getattr(b, 'business_verified', False)),
            'active_listings': active_count,
            'store_url': url_for('main.business_storefront', username=(b.username or '').lstrip('@')),
            'is_business_account': True,
            'wa_phone': wa_phone,
            'email': contact_email
        })

    return jsonify({
        'businesses': results,
        'total': len(results)
    })


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

# ============================================================
# CRITICAL STATIC PAGES — must be early so base.html footer
# (used by every page including index) can always url_for them.
# These were missing on the deployed PA version, causing the
# BuildError for 'main.terms' (and privacy/guidelines).
# ============================================================
@main_bp.route('/terms')
def terms():
    return render_template('main/terms.html')


@main_bp.route('/privacy')
def privacy():
    return render_template('main/privacy.html')


@main_bp.route('/guidelines')
def guidelines():
    return render_template('main/guidelines.html')


@main_bp.route('/how-it-works')
def how_it_works():
    monthly_views = get_current_month_views()
    return render_template('main/how_it_works.html', 
                           unlimited_passes=UNLIMITED_PASSES,
                           monthly_views=monthly_views)


@main_bp.route('/press')
def press():
    """Official Press & Media hub. Easy to extend by updating press_releases.py"""
    return render_template('main/press.html', releases=PRESS_RELEASES)


@main_bp.route('/press/print/<string:release_id>')
def press_print(release_id):
    """Clean, print-optimized standalone view for generating beautiful PDFs.
    Open this page then use browser Print > Save as PDF.
    """
    release = next((r for r in PRESS_RELEASES if r.get('id') == release_id), None)
    if not release:
        abort(404)
    return render_template('main/press_print.html', release=release)


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
# Grok AI Chat endpoint (2 free questions per calendar day SAST, then 1 credit)
# Fully free Polish handled in listings blueprint. Rate limits + quota display.
# ============================================================
@main_bp.route('/api/ai/ask', methods=['POST'])
@login_required
def ai_ask_listing():
    ensure_daily_free_credits(current_user)

    data = request.get_json() or {}
    listing_id = data.get('listing_id')
    question = (data.get('question') or '').strip()

    if not listing_id or not question:
        return jsonify({'error': 'Missing listing_id or question'}), 400

    listing = Listing.query.get_or_404(listing_id)

    # === Rate limit first (chat specific: 6/hour) ===
    try:
        allowed, rate_msg = current_user.check_ai_rate_limit(action='chat', max_per_hour=6)
        if not allowed:
            return jsonify({'error': rate_msg}), 429
    except Exception:
        # Defensive: on first-run table issues, allow the request (rate limiting is best-effort)
        pass

    # === Daily free quota using dedicated model (midnight SAST reset) ===
    has_unlimited = current_user.has_active_unlimited_pass()
    remaining_free = current_user.get_remaining_free_chat()
    is_free = (remaining_free > 0) or has_unlimited

    if not is_free:
        if (current_user.credit_balance or Decimal('0')) < Decimal('1'):
            return jsonify({
                'error': 'You have used your 2 free questions today. Additional questions cost 1 credit each.'
            }), 402
        current_user.credit_balance = (current_user.credit_balance or Decimal('0')) - Decimal('1')

    # Record usage
    current_user.record_ai_chat_use(used_free=is_free and not has_unlimited)
    current_user.record_ai_action()

    tx_amount = Decimal('0') if (is_free or has_unlimited) else Decimal('-1')
    tx = CreditTransaction(
        user_id=current_user.id,
        amount=tx_amount,
        transaction_type='ai_query',
        reference=f'listing_{listing_id}'
    )
    db.session.add(tx)
    db.session.commit()

    # Recompute remaining for response
    new_remaining = current_user.get_remaining_free_chat()

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
            'remaining_free_today': new_remaining
        })

    except requests.exceptions.RequestException as e:
        db.session.rollback()
        return jsonify({'error': 'Sorry, the AI service is temporarily unavailable. Please try again in a moment.'}), 503
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Unexpected error processing your question.'}), 500


# ============================================================
# Business Storefront (VOL-UI-STOREFRONT-ROBUST-2026-06-23)
# Never 404 on "View Store" clicks. Gracefully handles @prefix/case/whitespace
# variations from links or prod/dev data drift. Redirects + flash for bad cases.
# Public storefront only shows currently fresh (non-expired) + active listings
# using the same 7-day freshness rule as homepage/directory.
# ============================================================
@main_bp.route('/store/<string:username>')
def business_storefront(username):
    """Robust public storefront. Handles username formatting drift.
    /store/valid-business -> storefront (only fresh/non-expired + active listings)
    /store/malformed or non-business -> flash + redirect (directory or home)
    """
    # Clean input (strip @, whitespace)
    clean_username = (username or '').strip().lstrip('@')

    # Layered lookup (primary exact -> @ variant -> case-insensitive fallbacks)
    # Works on both SQLite (dev) and PostgreSQL (prod)
    user = User.query.filter_by(username=clean_username).first()
    if not user:
        user = User.query.filter_by(username='@' + clean_username).first()
    if not user:
        user = User.query.filter(User.username.ilike(clean_username)).first()
    if not user:
        user = User.query.filter(User.username.ilike('@' + clean_username)).first()

    if not user:
        flash("Store not found. Browse our Business Directory instead.", "info")
        return redirect(url_for('main.directory'))

    # Business validation (support legacy is_business flag + is_business_account property)
    if not getattr(user, 'is_business_account', False) and not getattr(user, 'is_business', False):
        flash("This profile belongs to a personal seller. Businesses have dedicated storefronts.", "info")
        return redirect(url_for('main.index'))

    # Public storefront: only non-expired (fresh within 7 days) + is_active=True listings.
    # This ensures "View Store" never shows stale/expired ads (matches homepage, directory counts, etc.).
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    # Use full freshness (refreshed_at preferred for reposts per v1.2) to match is_expired semantics
    freshness = func.coalesce(Listing.refreshed_at, Listing.last_reposted_at, Listing.created_at)

    active_listings = (Listing.query
        .options(joinedload(Listing.user))
        .filter(
            Listing.user_id == user.id,
            Listing.is_active == True,
            freshness >= seven_days_ago,
        )
        .order_by(Listing.is_promoted.desc(), freshness.desc())
        .all())

    return render_template('main/business_storefront.html',
                           business_user=user,
                           listings=active_listings)


@main_bp.route('/directory')
def directory():
    """Full Business Directory page (SEO + direct access).
    Also used as the content source for homepage toggle.
    """
    # Optional server-side initial filter params
    q = request.args.get('q', '')
    town = request.args.get('town', '')
    category = request.args.get('category', '')

    # Load a reasonable set server-side for non-JS fallback
    businesses_query = User.query.filter(
        db.or_(
            User.is_business == True,
            User.account_type == 'business',
            User.business_name.isnot(None)  # catch legacy / profile-upgraded accounts
        )
    ).order_by(
        User.business_verified.desc(),
        User.business_name.asc().nullslast()
    ).limit(48)

    if q:
        like = f'%{q}%'
        businesses_query = businesses_query.filter(
            db.or_(
                User.business_name.ilike(like),
                User.username.ilike(like)
            )
        )
    if town:
        businesses_query = businesses_query.filter(User.location == town)
    if category:
        businesses_query = businesses_query.filter(User.business_type == category)

    businesses = businesses_query.all()

    # Pre-compute active counts (small N)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    freshness = func.coalesce(Listing.last_reposted_at, Listing.created_at)

    business_data = []
    for b in businesses:
        active_count = Listing.query.filter(
            Listing.user_id == b.id,
            Listing.is_active == True,
            freshness >= seven_days_ago
        ).count()
        business_data.append({
            'user': b,
            'active_listings': active_count
        })

    return render_template('main/directory.html',
                           businesses=business_data,
                           q=q, town=town, category=category)
