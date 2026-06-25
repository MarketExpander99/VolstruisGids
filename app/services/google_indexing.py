# app/services/google_indexing.py
"""
Google Indexing API integration for VolstruisGids.

Tells Google "this URL is new/updated" or "remove this URL" so new listings
appear in search results much faster (minutes/hours instead of days).

Setup (one-time):
1. Google Cloud Console -> new project -> enable Indexing API
2. IAM -> Service Accounts -> create one with role "Indexing API Indexer"
3. Keys tab -> create JSON key -> rename to volstruisgids-indexing-key.json
4. Place the file in config/ (gitignored) or set GOOGLE_INDEXING_KEY_FILE env.

Usage (after db.session.commit() on a listing):
    from app.services.google_indexing import notify_listing_change
    listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
    notify_listing_change(listing_url, action='URL_UPDATED')

For removal (mark-sold, delete, deactivate):
    notify_listing_change(listing_url, action='URL_DELETED')
"""

import logging
import os
import requests

logger = logging.getLogger(__name__)

try:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GoogleRequest
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False


class GoogleIndexingService:
    """
    Thin wrapper around Google's Indexing API.
    Safe to use even if key is missing (no-ops gracefully).
    """

    SCOPES = ["https://www.googleapis.com/auth/indexing"]
    ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"

    def __init__(self, key_path: str = None):
        self.credentials = None
        self.key_path = key_path
        self._load_credentials()

    def _resolve_key_path(self) -> str | None:
        """Resolve the service account key file from arg, env, config, or default."""
        candidates = []

        if self.key_path:
            candidates.append(self.key_path)

        env_path = os.getenv('GOOGLE_INDEXING_KEY_FILE')
        if env_path:
            candidates.append(env_path)

        # Try Flask config if we are inside an app context
        try:
            from flask import current_app
            if current_app:
                cfg = current_app.config.get('GOOGLE_INDEXING_KEY_FILE')
                if cfg:
                    candidates.append(cfg)
        except Exception:
            pass  # no app context or not configured yet

        # Project default (matches spec + our config.py)
        candidates.append('config/volstruisgids-indexing-key.json')

        for p in candidates:
            if p and os.path.exists(p):
                return p

        return None

    def _load_credentials(self):
        if not GOOGLE_AUTH_AVAILABLE:
            logger.warning("google-auth not installed — Google Indexing disabled")
            return

        key_path = self._resolve_key_path()
        if not key_path:
            logger.info("Google Indexing key not found (expected in dev or before setup). Skipping.")
            return

        try:
            self.credentials = service_account.Credentials.from_service_account_file(
                key_path, scopes=self.SCOPES
            )
            logger.info(f"Google Indexing service account loaded from {key_path}")
        except Exception as e:
            logger.error(f"Failed to load Google Indexing key at {key_path}: {e}")
            self.credentials = None

    def notify_url(self, url: str, action: str = "URL_UPDATED") -> bool:
        """
        Send URL notification to Google.

        action:
            "URL_UPDATED"  -> new or changed page (most common)
            "URL_DELETED"  -> page permanently removed from search
        """
        if not self.credentials:
            # Either no key or packages missing — silently skip
            return False

        if not url or not url.startswith(('http://', 'https://')):
            logger.warning(f"Skipping Google notify — invalid URL: {url}")
            return False

        if action not in ("URL_UPDATED", "URL_DELETED"):
            action = "URL_UPDATED"

        try:
            # Refresh token
            self.credentials.refresh(GoogleRequest())

            payload = {"url": url, "type": action}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.credentials.token}",
            }

            resp = requests.post(
                self.ENDPOINT,
                headers=headers,
                json=payload,
                timeout=10,
            )

            if resp.status_code == 200:
                logger.info(f"Google Indexing notified ({action}): {url}")
                return True
            else:
                logger.error(f"Google Indexing error {resp.status_code}: {resp.text}")
                return False

        except Exception as e:
            logger.error(f"Google Indexing request failed for {url}: {e}")
            return False


# Convenience function for routes (recommended usage)
_service = None

def get_indexing_service() -> GoogleIndexingService:
    global _service
    if _service is None:
        _service = GoogleIndexingService()
    return _service


def notify_listing_change(url: str, action: str = "URL_UPDATED") -> bool:
    """
    Safe one-liner to notify Google about a listing URL change.
    Never raises — failures are logged only.
    """
    try:
        svc = get_indexing_service()
        return svc.notify_url(url, action)
    except Exception as e:
        logger.error(f"notify_listing_change failed: {e}")
        return False
