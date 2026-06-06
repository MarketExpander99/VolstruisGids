import os
from dotenv import load_dotenv

load_dotenv()

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