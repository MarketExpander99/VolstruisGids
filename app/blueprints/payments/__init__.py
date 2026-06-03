from flask import Blueprint

payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

# Import routes here to avoid circular imports
from . import routes