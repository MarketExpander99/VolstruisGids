from flask import Flask, app, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from app.config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure external URLs (for payment redirects) use the correct scheme in production
    if app.config.get('PREFERRED_URL_SCHEME'):
        app.config['PREFERRED_URL_SCHEME'] = app.config['PREFERRED_URL_SCHEME']

    # === YOCO DEBUG AT STARTUP ===
    print("=== YOCO CONFIG DEBUG (at app startup) ===")
    flask_env = app.config.get('FLASK_ENV')
    yoco_test_mode = app.config.get('YOCO_TEST_MODE')
    yoco_key = app.config.get('YOCO_SECRET_KEY')
    test_key = app.config.get('YOCO_TEST_SECRET_KEY')
    live_key = app.config.get('YOCO_LIVE_SECRET_KEY')
    raw_key = app.config.get('YOCO_SECRET_KEY_RAW')
    print(f"FLASK_ENV: {flask_env}")
    print(f"YOCO_TEST_MODE: {yoco_test_mode}")
    print(f"YOCO_SECRET_KEY present: {bool(yoco_key)}")
    if yoco_key:
        print(f"YOCO_SECRET_KEY prefix: {yoco_key[:15]}... (len={len(yoco_key)})")
    print(f"YOCO_TEST_SECRET_KEY present: {bool(test_key)}")
    if test_key:
        print(f"YOCO_TEST_SECRET_KEY prefix: {test_key[:15]}... (len={len(test_key)})")
    print(f"YOCO_LIVE_SECRET_KEY present: {bool(live_key)}")
    if live_key:
        print(f"YOCO_LIVE_SECRET_KEY prefix: {live_key[:15]}... (len={len(live_key)})")
    print(f"YOCO_SECRET_KEY_RAW (plain) present: {bool(raw_key)}")
    print("=== END YOCO DEBUG ===")
    # === END DEBUG ===

    # === STRIPE DEBUG AT STARTUP (per credit/sub spec) ===
    print("=== STRIPE CONFIG DEBUG (at app startup) ===")
    stripe_pk = app.config.get('STRIPE_PUBLISHABLE_KEY')
    stripe_sk = app.config.get('STRIPE_SECRET_KEY')
    stripe_wh = app.config.get('STRIPE_WEBHOOK_SECRET')
    print(f"STRIPE_PUBLISHABLE_KEY present: {bool(stripe_pk)}")
    if stripe_pk:
        print(f"STRIPE_PUBLISHABLE_KEY prefix: {stripe_pk[:12]}... (len={len(stripe_pk)})")
    print(f"STRIPE_SECRET_KEY present: {bool(stripe_sk)}")
    if stripe_sk:
        print(f"STRIPE_SECRET_KEY prefix: {stripe_sk[:12]}... (len={len(stripe_sk)})")
    print(f"STRIPE_WEBHOOK_SECRET present: {bool(stripe_wh)}")
    print("=== END STRIPE DEBUG ===")
    # === END STRIPE DEBUG ===

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # Import all models inside create_app to ensure relationships are registered
    from app.models.user import User
    from app.models.category import Category
    from app.models.listing import Listing
    from app.models.promotion import Promotion
    from app.models.message import Message
    from app.models.payment import Payment
    from app.models.credit_transaction import CreditTransaction  # Credit System v1.0
    from app.models.payment_transaction import PaymentTransaction  # Stripe credit + sub transactions (spec v1)
    from app.models.user_credit_pass import UserCreditPass  # Unlimited Credit Passes (PAYG-UNLIMITED-2026-06-20)
    from app.models.site_stat import SiteStat  # Site hit counter / global views
    from app.models.user_ai_usage import UserAIUsage  # Daily free Grok chat quota (v1.1 free AI spec)
    from app.models.like import Like
    from app.models.comment import Comment
    from app.models.psa_banner import PSABanner  # PSA / News banners (VGS-004)

    # Safe DB column updates for Credit System v1.1 (refreshed_at / credits / free tier)
    # Run inside app context so inspector/engine access is valid
    with app.app_context():
        try:
            from app.utils.safe_db_updates import apply_safe_db_updates
            apply_safe_db_updates(db)
        except Exception as e:
            print(f"[safe_db_updates] Non-fatal: {e}")

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp
    from app.blueprints.listings import listings_bp
    from app.blueprints.profile import profile_bp
    from app.blueprints.payments import payments_bp   # <-- Added for Paystack integration
    from app.blueprints.messages import messages_bp   # <-- Private Messaging MVP
    from app.blueprints.sitemap import sitemap_bp
    from app.blueprints.admin import admin_bp
    from app.utils.admin import is_admin

    app.register_blueprint(sitemap_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(listings_bp)
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(payments_bp)   # <-- Added (url_prefix='/payments' is defined inside the blueprint)
    app.register_blueprint(messages_bp)   # <-- /messages/inbox, /messages/conversation etc.
    app.register_blueprint(admin_bp)      # <-- /admin (protected by ADMIN_USERNAMES)

    # ============================================================
    # Custom 404 handler (VGD-SPEC-2026-06-23-001)
    # Branded ostrich-friendly page + structured logging for store + all 404s.
    # ============================================================
    @app.errorhandler(404)
    def page_not_found(e):
        try:
            app.logger.warning(
                "404 Not Found",
                extra={
                    'path': request.path,
                    'referrer': getattr(request, 'referrer', None),
                    'user_agent': request.headers.get('User-Agent') if request else None,
                    'method': request.method if request else None,
                }
            )
        except Exception:
            pass  # Never let logging break error response

        # Provide context for ghost/expired listing friendly message (used by SEO-REMOVE-GHOST-LISTINGS).
        # Heuristic on path is cheap and catches the common case of old search result links to /listing/<id>
        # that no longer exist or are expired/inactive. Non-listing 404s won't trigger the special text.
        is_ghost_listing = bool(request and ('/listings/listing/' in (getattr(request, 'path', '') or '') or '/listing/' in (getattr(request, 'path', '') or '')))
        return render_template('errors/404.html', is_ghost_listing=is_ghost_listing), 404

    # Context processor to provide unread message count for navbar notifications (NEW messages only)
    @app.context_processor
    def inject_unread_messages_count():
        if current_user.is_authenticated:
            # Count only unread messages received by the current user
            unread_count = Message.query.filter(
                Message.receiver_id == current_user.id,
                Message.read == False
            ).count()
            return {'unread_messages_count': unread_count}
        return {'unread_messages_count': 0}

    # Currency / price filter: R 1,234.00 format for easy reading
    def currency(value):
        if value is None or value == '':
            return ''
        try:
            val = float(value)
            return f"R {val:,.2f}"
        except (ValueError, TypeError):
            return f"R {value}"
    app.template_filter('currency')(currency)

    # Expose select Python builtins to Jinja templates (e.g. hasattr for defensive checks on models)
    # Fixes "UndefinedError: 'hasattr' is undefined" on pages using _listing_cards.html (business storefront, category, etc.)
    app.jinja_env.globals['hasattr'] = hasattr

    # Admin status for conditional nav (spec: link visible only to admin)
    @app.context_processor
    def inject_admin_flag():
        try:
            return {'is_admin_user': bool(is_admin())}
        except Exception:
            return {'is_admin_user': False}

    # Active PSA / News banners for frontend display (VGS-004 + VGS-004b)
    # - DB banners (admin-managed) + system-generated user-specific for own expired/soon-expiring listings.
    # Queried once per request. System banners are light dynamic objects (no DB rows).
    # Per-user dismissal respected (via dismissed_psa_banners JSON) for all logged-in users.
    @app.context_processor
    def inject_active_psa_banners():
        try:
            from datetime import datetime as dt, timedelta
            from app.models.psa_banner import PSABanner
            from app.models.listing import Listing
            from app.utils.admin import is_admin
            from types import SimpleNamespace
            from flask import url_for as _url_for

            now = dt.utcnow()
            db_banners = (
                PSABanner.query
                .filter(
                    PSABanner.active == True,
                    (PSABanner.expiry == None) | (PSABanner.expiry > now)
                )
                .order_by(PSABanner.priority.desc(), PSABanner.created_at.desc())
                .limit(5)  # safety cap
                .all()
            )

            # Dismissed set (support list/JSON-string, ints or synthetic negative ints)
            dismissed_set = set()
            if current_user.is_authenticated:
                try:
                    dismissed = current_user.dismissed_psa_banners or []
                    if isinstance(dismissed, str):
                        import json
                        try:
                            dismissed = json.loads(dismissed) or []
                        except Exception:
                            dismissed = []
                    dismissed_set = {int(x) for x in (dismissed or []) if x is not None}
                except Exception:
                    dismissed_set = set()

            # Filter global DB banners for non-admins only (admins preview everything)
            banners = db_banners
            if current_user.is_authenticated:
                try:
                    if not is_admin(current_user):
                        banners = [b for b in db_banners if getattr(b, 'id', None) not in dismissed_set]
                except Exception:
                    banners = db_banners

            # ============================================================
            # VGS-004b: System-generated PSA for current user's own listings
            # - Expired: "has expired. Reactivate..."
            # - Soon (< 3 days): "expires soon. Renew now!"
            # Synthetic negative IDs (no collision with real PSA ids) so reuse dismiss + template.
            # Only for owners; max 1 expired + 1 expiring; respect same dismissed store.
            # Links go to /my-listings (where repost button appears for expired).
            # ============================================================
            system_banners = []
            if current_user.is_authenticated:
                try:
                    DAYS_SOON = 3
                    soon_threshold = now + timedelta(days=DAYS_SOON)

                    # Efficient owner-only queries (is_active=True to ignore sold)
                    expired_ones = (
                        Listing.query
                        .filter(
                            Listing.user_id == current_user.id,
                            Listing.is_active == True,
                            Listing.expires_at <= now
                        )
                        .order_by(Listing.expires_at.asc())
                        .limit(1)
                        .all()
                    )
                    expiring_soon = (
                        Listing.query
                        .filter(
                            Listing.user_id == current_user.id,
                            Listing.is_active == True,
                            Listing.expires_at > now,
                            Listing.expires_at <= soon_threshold
                        )
                        .order_by(Listing.expires_at.asc())
                        .limit(1)
                        .all()
                    )

                    # Expired banner first (higher urgency)
                    for l in expired_ones:
                        sid = -(100000 + getattr(l, 'id', 0))
                        if sid in dismissed_set:
                            continue
                        title = f"Your listing '{(getattr(l, 'title', 'Listing') or '')[:55]}' has expired."
                        system_banners.append(SimpleNamespace(
                            id=sid,
                            title=title,
                            content="Reactivate to keep it visible!",
                            color='danger',
                            banner_type='alert',
                            link=_url_for('main.my_listings'),
                        ))
                        break  # max 1

                    # Then expiring (if room)
                    for l in expiring_soon:
                        sid = -(200000 + getattr(l, 'id', 0))
                        if sid in dismissed_set:
                            continue
                        title = f"Your listing '{(getattr(l, 'title', 'Listing') or '')[:55]}' expires soon."
                        system_banners.append(SimpleNamespace(
                            id=sid,
                            title=title,
                            content="Renew now!",
                            color='warning',
                            banner_type='psa',
                            link=_url_for('main.my_listings'),
                        ))
                        break  # max 1

                except Exception:
                    # Non-fatal: never break page load for banner gen
                    system_banners = []

            # Prioritize system (personal, actionable) then any global banners
            combined = system_banners + banners
            return {'active_psa_banners': combined}
        except Exception:
            # Table may not exist yet on first boot, or other transient issue
            return {'active_psa_banners': []}

    return app