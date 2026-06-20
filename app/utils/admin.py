"""
Admin utilities for VolstruisGids
Environment-based admin access (no DB flag).
Provides @admin_required decorator and simple file audit logging.
"""

import os
import logging
import secrets
import string
from functools import wraps
from datetime import datetime

from flask import abort, current_app
from flask_login import current_user


def get_admin_usernames():
    """Return list of admin usernames from ADMIN_USERNAMES env var (comma-separated).
    Falls back to config if present. Strips whitespace.
    """
    raw = os.environ.get('ADMIN_USERNAMES') or current_app.config.get('ADMIN_USERNAMES', '')
    if not raw:
        return []
    return [u.strip() for u in str(raw).split(',') if u.strip()]


def is_admin(user=None):
    """Check if the given (or current) user is an admin by username (or email as fallback).
    """
    if user is None:
        user = current_user
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    admins = get_admin_usernames()
    if user.username and user.username in admins:
        return True
    if getattr(user, 'email', None) and user.email in admins:
        return True
    return False


def admin_required(f):
    """Decorator: require authenticated admin user. Returns 403 otherwise."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not (current_user.is_authenticated and is_admin(current_user)):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# --- Audit logging (file based, no schema changes) ---

_admin_logger = None

def _get_admin_logger():
    global _admin_logger
    if _admin_logger is not None:
        return _admin_logger
    try:
        log_dir = 'instance'
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'admin_audit.log')
        logger = logging.getLogger('volstruisgids.admin_audit')
        logger.setLevel(logging.INFO)
        # Avoid duplicate handlers on reloads
        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            fh = logging.FileHandler(log_path, encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
            logger.addHandler(fh)
        _admin_logger = logger
    except Exception:
        # Fallback to root if anything fails
        _admin_logger = logging.getLogger(__name__)
    return _admin_logger


def log_admin_action(action, target_type, target_id, details=""):
    """Record admin action in a simple append-only log file.
    Safe, zero-DB migration, easy to tail or parse.
    """
    try:
        admin_name = getattr(current_user, 'username', 'anonymous') if current_user and current_user.is_authenticated else 'system'
        msg = f"ADMIN={admin_name} ACTION={action} TARGET={target_type}:{target_id}"
        if details:
            msg += f" DETAILS={details}"
        _get_admin_logger().info(msg)
        # Dev visibility
        print(f"[ADMIN-AUDIT] {msg}")
    except Exception as exc:
        print(f"[ADMIN-AUDIT-ERROR] {exc}")


def generate_temp_password(length=10):
    """Generate a reasonably strong temporary password for admin resets."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one of each broad class for friendliness
    pw = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
    ]
    pw += [secrets.choice(alphabet) for _ in range(max(0, length - len(pw)))]
    secrets.SystemRandom().shuffle(pw)
    return ''.join(pw)
