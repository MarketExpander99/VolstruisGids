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
        self.secret_key = current_app.config.get('YOCO_SECRET_KEY')
        self.api_base = current_app.config.get('YOCO_API_BASE', 'https://api.yoco.com')
        self.checkouts_url = f"{self.api_base}/v1/checkouts"
        if not self.secret_key:
            raise ValueError("YOCO_SECRET_KEY not configured")

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
            logger.error(f"Yoco create_checkout failed: {str(e)}")
            raise Exception(f"Yoco API error: {str(e)}") from e

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
            # Yoco typically sends signature as hex or 'sha256=xxx'
            provided = signature.split('=')[-1] if '=' in signature else signature
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