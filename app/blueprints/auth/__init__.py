from flask import Blueprint

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Import routes here to avoid circular imports
from . import routes