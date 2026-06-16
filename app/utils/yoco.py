"""
Yoco Payment Gateway Client - VolstruisGids
Clean, production-ready helper that correctly handles live vs test keys.
"""

import os
import requests
from flask import current_app
from typing import Optional, Dict, Any


class YocoClient:
    """Simple Yoco API client with proper live/test key handling."""

    BASE_URL = "https://payments.yoco.com/api"

    def __init__(self):
        self.test_mode = os.environ.get("YOCO_TEST_MODE", "true").lower() == "true"

        if self.test_mode:
            self.secret_key = (
                os.environ.get("YOCO_TEST_SECRET_KEY")
                or os.environ.get("YOCO_SECRET_KEY")
            )
        else:
            self.secret_key = (
                os.environ.get("YOCO_LIVE_SECRET_KEY")
                or os.environ.get("YOCO_SECRET_KEY")
            )

        if not self.secret_key:
            raise ValueError(
                "No Yoco secret key found. "
                "Set YOCO_LIVE_SECRET_KEY (or YOCO_SECRET_KEY) when YOCO_TEST_MODE=false"
            )

        # Safety check
        if not self.test_mode and not self.secret_key.startswith("sk_live_"):
            current_app.logger.warning(
                "YOCO_TEST_MODE is false but the key does not start with sk_live_. "
                "Double-check your environment variables."
            )

    @property
    def is_live(self) -> bool:
        return not self.test_mode

    def create_checkout(
        self,
        amount: int,
        currency: str = "ZAR",
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a Yoco checkout session.
        Returns the response dict from Yoco (contains redirect_url, id, etc).
        """
        url = f"{self.BASE_URL}/checkouts"

        payload = {
            "amount": amount,
            "currency": currency,
            "successUrl": success_url,
            "cancelUrl": cancel_url,
            "metadata": metadata or {},
        }

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            current_app.logger.error(f"Yoco create_checkout error: {e.response.text}")
            raise
        except Exception as e:
            current_app.logger.exception("Unexpected error calling Yoco API")
            raise
