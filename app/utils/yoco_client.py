"""
Yoco Checkout API Client
Production-ready helper for Yoco integration (replaces Paystack).

Usage:
    from app.utils.yoco_client import YocoClient
    client = YocoClient()
    checkout = client.create_checkout(amount_cents=..., success_url=..., cancel_url=..., metadata=...)
    # checkout['redirect_url'], checkout['id']
"""

import os
import requests
import hmac
import hashlib
import json
from flask import current_app
import logging

logger = logging.getLogger(__name__)

class YocoClient:
    def __init__(self):
        raw_key = current_app.config.get('YOCO_SECRET_KEY')
        self.secret_key = raw_key.strip() if raw_key else None
        self.api_base = current_app.config.get('YOCO_API_BASE', 'https://api.yoco.com')
        self.checkouts_url = f"{self.api_base}/v1/checkouts"
        if not self.secret_key:
            raise ValueError("YOCO_SECRET_KEY not configured. Add YOCO_LIVE_SECRET_KEY or YOCO_SECRET_KEY (or YOCO_TEST_SECRET_KEY) to your .env.")
        if not self.secret_key.startswith('sk_'):
            raise ValueError("YOCO_SECRET_KEY must be a secret key starting with 'sk_' (not a publishable key starting with 'pk_'). Copy the Secret key from your Yoco dashboard.")

        # Debug: log prefix only (safe, never log full secret) — dev only
        flask_env = current_app.config.get('FLASK_ENV')
        if flask_env == 'development':
            key_prefix = self.secret_key[:15] + "..." if self.secret_key else "None"
            print(f"DEBUG: YocoClient __init__ using key starting with {key_prefix} (FLASK_ENV={flask_env}, key length={len(self.secret_key) if self.secret_key else 0})")
            logger.info(f"YocoClient using key starting with {key_prefix} (FLASK_ENV={flask_env}, key length={len(self.secret_key) if self.secret_key else 0})")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": os.urandom(16).hex()  # prevent duplicate checkouts
        }

    def create_checkout(self, amount_cents: int, success_url: str, cancel_url: str, 
                        failure_url: str = None, metadata: dict = None, 
                        currency: str = "ZAR", description: str = None):
        """
        Create a Yoco Checkout session.
        Returns dict with 'id' and 'redirect_url' on success.
        """
        if amount_cents < 100:  # minimum 1 ZAR = 100 cents for most cases
            raise ValueError("Amount too small for Yoco checkout")

        payload = {
            "amount": amount_cents,
            "currency": currency,
            "successUrl": success_url,
            "cancelUrl": cancel_url,
        }
        if failure_url:
            payload["failureUrl"] = failure_url
        if metadata:
            payload["metadata"] = metadata
        if description:
            payload["description"] = description

        try:
            response = requests.post(
                self.checkouts_url,
                json=payload,
                headers=self._headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Yoco checkout created: {data.get('id')}")
            return {
                "id": data["id"],
                "redirect_url": data["redirectUrl"],
                "status": data.get("status"),
                "metadata": data.get("metadata", {})
            }
        except requests.RequestException as e:
            error_body = ""
            if 'response' in locals() and hasattr(response, 'text'):
                error_body = f" | Response body: {response.text}"
            logger.error(f"Yoco create_checkout failed: {str(e)}{error_body}")
            raise Exception(f"Yoco API error: {str(e)}{error_body}") from e

        # Note: legacy create path is no longer primary (new YocoClient in utils/yoco.py is used for checkout creation).
        # The old test-only assertions below were removed to fully support live sk_live_ keys in production.

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Yoco webhook signature using webhook secret.
        Yoco uses HMAC-SHA256 on the raw payload.
        """
        webhook_secret = current_app.config.get('YOCO_WEBHOOK_SECRET')
        if not webhook_secret or not signature:
            logger.warning("Missing YOCO_WEBHOOK_SECRET or signature header")
            return False

        try:
            computed = hmac.new(
                webhook_secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()

            # Yoco / Standard Webhooks formats:
            # - raw hex
            # - sha256=xxx
            # - t=...,v1=thesig   (Standard Webhooks style)
            provided = signature
            if "=" in provided:
                # Take the last value after = , or look for v1=
                if "v1=" in provided:
                    provided = provided.split("v1=")[-1].split(",")[0].strip()
                else:
                    provided = provided.split("=")[-1].strip()
            return hmac.compare_digest(computed, provided)
        except Exception as e:
            logger.error(f"Webhook signature verification error: {e}")
            return False

    def get_checkout(self, checkout_id: str):
        """Optional: retrieve checkout status"""
        url = f"{self.checkouts_url}/{checkout_id}"
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch Yoco checkout {checkout_id}: {e}")
            return None

    # ============================================================
    # WEBHOOK MANAGEMENT (for when you can't use the Yoco UI)
    # ============================================================

    def register_webhook(self, url: str, name: str = "VolstruisGids", events: list = None):
        """
        Register a new webhook endpoint via the Yoco API.
        The signing secret is returned only ONCE - save it immediately as YOCO_WEBHOOK_SECRET.
        Returns the full webhook object from Yoco.
        """
        # Yoco Checkout/Online API for webhooks uses payments.yoco.com
        webhook_base = "https://payments.yoco.com/api/webhooks"
        payload = {
            "name": name,
            "url": url,
        }
        if events:
            payload["events"] = events
        # Some accounts may require events; if not provided Yoco may default or error.

        try:
            response = requests.post(
                webhook_base,
                json=payload,
                headers=self._headers(),
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Yoco webhook registered: {data.get('id')}")
            print("✅ Webhook registered successfully!")
            print("   Full response (save the secret if present - shown only once):")
            print(data)
            return data
        except requests.RequestException as e:
            error_body = ""
            if hasattr(e, 'response') and e.response is not None:
                error_body = f" | Response: {e.response.text}"
            logger.error(f"Yoco register_webhook failed: {str(e)}{error_body}")
            print(f"❌ Failed to register webhook: {e}{error_body}")
            raise

    def list_webhooks(self):
        """List existing webhooks registered for this account."""
        webhook_base = "https://payments.yoco.com/api/webhooks"
        try:
            response = requests.get(
                webhook_base,
                headers=self._headers(),
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            print("Current webhooks:")
            print(data)
            return data
        except Exception as e:
            logger.error(f"Failed to list Yoco webhooks: {e}")
            print(f"Error listing webhooks: {e}")
            return None

    def delete_webhook(self, webhook_id: str):
        """Delete a webhook by its id."""
        webhook_base = f"https://payments.yoco.com/api/webhooks/{webhook_id}"
        try:
            response = requests.delete(
                webhook_base,
                headers=self._headers(),
                timeout=10
            )
            response.raise_for_status()
            print(f"✅ Deleted webhook {webhook_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete webhook {webhook_id}: {e}")
            print(f"Error deleting: {e}")
            return False