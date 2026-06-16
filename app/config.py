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

    # Active key selection (use TEST in dev, LIVE in prod)
    YOCO_SECRET_KEY = YOCO_TEST_SECRET_KEY if FLASK_ENV == 'development' else YOCO_LIVE_SECRET_KEY

    YOCO_API_BASE = 'https://api.yoco.com'
    YOCO_CHECKOUTS_URL = f'{YOCO_API_BASE}/v1/checkouts'

# After class definition, we can add debug when module loads, but better in create_app
# The debug will be printed in create_app below.