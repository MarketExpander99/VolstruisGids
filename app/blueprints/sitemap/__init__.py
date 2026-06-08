from flask import Blueprint

sitemap_bp = Blueprint('sitemap', __name__)

from . import routes