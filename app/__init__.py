from flask import Flask, app
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

    # === YOCO DEBUG AT STARTUP ===
    print("=== YOCO CONFIG DEBUG (at app startup) ===")
    flask_env = app.config.get('FLASK_ENV')
    yoco_key = app.config.get('YOCO_SECRET_KEY')
    test_key = app.config.get('YOCO_TEST_SECRET_KEY')
    live_key = app.config.get('YOCO_LIVE_SECRET_KEY')
    print(f"FLASK_ENV: {flask_env}")
    print(f"YOCO_SECRET_KEY present: {bool(yoco_key)}")
    if yoco_key:
        print(f"YOCO_SECRET_KEY prefix: {yoco_key[:15]}... (len={len(yoco_key)})")
    print(f"YOCO_TEST_SECRET_KEY present: {bool(test_key)}")
    if test_key:
        print(f"YOCO_TEST_SECRET_KEY prefix: {test_key[:15]}... (len={len(test_key)})")
    print(f"YOCO_LIVE_SECRET_KEY present: {bool(live_key)}")
    if live_key:
        print(f"YOCO_LIVE_SECRET_KEY prefix: {live_key[:15]}... (len={len(live_key)})")
    print("=== END YOCO DEBUG ===")
    # === END DEBUG ===

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

    app.register_blueprint(sitemap_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(listings_bp)
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(payments_bp)   # <-- Added (url_prefix='/payments' is defined inside the blueprint)
    app.register_blueprint(messages_bp)   # <-- /messages/inbox, /messages/conversation etc.

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

    return app