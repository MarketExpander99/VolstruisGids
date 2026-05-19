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
    # Additional production settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None