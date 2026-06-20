import os
from dotenv import load_dotenv

load_dotenv()

def _clean_env_value(val):
    """Strip whitespace and surrounding quotes from .env values."""
    if val is None:
        return None
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///volstruisgids.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FLASK_APP = 'run.py'
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'development'

    # URL scheme for external links (important for payment provider success/cancel URLs)
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME') or ('https' if FLASK_ENV == 'production' else 'http')

    # Flask-Login settings
    LOGIN_VIEW = 'auth.login'
    LOGIN_MESSAGE = 'Please log in to access this page.'
    LOGIN_MESSAGE_CATEGORY = 'info'

    # Flask-Migrate settings (handled via extension)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # === Grok / xAI API (added - no existing config removed) ===
    GROK_API_KEY = os.environ.get('GROK_API_KEY')
    GROK_API_URL = 'https://api.x.ai/v1/chat/completions'
    GROK_MODEL = 'grok-3'   # or 'grok-2-1212' if you prefer

    # === Yoco Checkout API (Paystack removed - pivot to Yoco) ===
    # Use SECRET keys (sk_test_... / sk_live_...) -- these are the ones for server-side API calls like creating checkouts.
    # Public/publishable keys (pk_test_... / pk_live_...) are ONLY for client-side JavaScript and will cause 401 Unauthorized.
    # Get your SECRET keys from the Yoco Dashboard (Developers > API Keys > look for the "Secret key" section, not Publishable).
    # Note: _clean_env_value handles common .env formatting issues like quotes or extra spaces
    YOCO_TEST_SECRET_KEY = _clean_env_value(os.getenv('YOCO_TEST_SECRET_KEY'))
    YOCO_LIVE_SECRET_KEY = _clean_env_value(os.getenv('YOCO_LIVE_SECRET_KEY'))
    YOCO_WEBHOOK_SECRET = _clean_env_value(os.getenv('YOCO_WEBHOOK_SECRET'))

    # Also support plain YOCO_SECRET_KEY (user's production deploys often set this + YOCO_LIVE + YOCO_TEST_MODE)
    YOCO_SECRET_KEY_RAW = _clean_env_value(os.getenv('YOCO_SECRET_KEY'))

    # YOCO_TEST_MODE logic (supports user's exact prod config: YOCO_TEST_MODE=false + live keys)
    test_mode_raw = os.getenv('YOCO_TEST_MODE', '').strip().lower()
    if test_mode_raw in ('true', '1', 'yes', 'on'):
        use_test_key = True
    elif test_mode_raw in ('false', '0', 'no', 'off'):
        use_test_key = False
    else:
        use_test_key = (FLASK_ENV == 'development')

    YOCO_TEST_MODE = 'true' if use_test_key else 'false'

    if use_test_key:
        YOCO_SECRET_KEY = YOCO_TEST_SECRET_KEY or YOCO_SECRET_KEY_RAW
    else:
        YOCO_SECRET_KEY = YOCO_LIVE_SECRET_KEY or YOCO_SECRET_KEY_RAW or YOCO_TEST_SECRET_KEY

    YOCO_API_BASE = 'https://api.yoco.com'
    YOCO_CHECKOUTS_URL = f'{YOCO_API_BASE}/v1/checkouts'

    # === Stripe (Checkout + Billing) for Credit Packs + Monthly Business Subscriptions (per spec v1) ===
    # Use test keys in development, live in prod. Never commit real keys.
    STRIPE_PUBLISHABLE_KEY = _clean_env_value(os.getenv('STRIPE_PUBLISHABLE_KEY'))
    STRIPE_SECRET_KEY = _clean_env_value(os.getenv('STRIPE_SECRET_KEY'))
    STRIPE_WEBHOOK_SECRET = _clean_env_value(os.getenv('STRIPE_WEBHOOK_SECRET'))

    # Active selection similar to Yoco (test when FLASK_ENV=development)
    # For Stripe we usually use the same key but env-aware for docs clarity
    STRIPE_API_KEY = STRIPE_SECRET_KEY

# After class definition, we can add debug when module loads, but better in create_app
# The debug will be printed in create_app below.