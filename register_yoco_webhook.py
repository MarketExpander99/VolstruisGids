#!/usr/bin/env python3
"""
Helper script to register a Yoco webhook via the API
(when you can't easily find / use the UI in the Yoco Business Portal).

Usage:
  1. Make sure your Flask server is running (for the /payments/yoco-webhook route to exist).
  2. Expose it publicly. On Windows the easiest is ngrok:
       ngrok http 5000
     (or whatever port your app runs on - check run.py or the console).
     Copy the https://....ngrok.io URL.

  3. Update your .env with a CLEAN (non-placeholder) YOCO_TEST_SECRET_KEY if you haven't already.
     Also make sure FLASK_ENV=development

  4. Run this script:
       python register_yoco_webhook.py

  5. When prompted, paste the full public webhook URL, e.g.
       https://abc123.ngrok.io/payments/yoco-webhook

  6. The script will call Yoco and print the result.
     - Look for an "id" (the webhook id)
     - **Very important**: Look for a "secret" or "signing_secret" or similar in the response.
       Yoco usually shows the webhook secret ONLY ONCE when you create it.
       Copy it immediately and put it in your .env as:
         YOCO_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxx

  7. Restart your Flask app completely after updating the secret.

  8. (Optional) Run the script again later with argument "list" to see registered webhooks:
       python register_yoco_webhook.py list

You can also delete by id:
  python register_yoco_webhook.py delete <webhook_id>

Security note: This uses your secret key from .env. Never commit real keys.
"""

import os
import sys
from dotenv import load_dotenv
from app import create_app
from app.utils.yoco_client import YocoClient

load_dotenv()

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "register"

    app = create_app()
    with app.app_context():
        client = YocoClient()

        if command == "list":
            print("Listing existing Yoco webhooks...")
            client.list_webhooks()
            return

        if command == "delete":
            if len(sys.argv) < 3:
                print("Usage: python register_yoco_webhook.py delete <webhook_id>")
                return
            wid = sys.argv[2]
            client.delete_webhook(wid)
            return

        # Default: register
        print("=== Yoco Webhook Registration (API) ===")
        print("This bypasses the UI.")
        print()

        # Prompt for the public URL
        default_hint = "https://YOUR-NGROK-SUBDOMAIN.ngrok.io/payments/yoco-webhook"
        url = input(f"Enter the FULL public webhook URL (e.g. {default_hint}):\n> ").strip()

        if not url or not url.startswith("https://"):
            print("ERROR: URL must start with https:// and be publicly reachable.")
            print("Use ngrok (or similar) for local development.")
            return

        name = input("Give this webhook a name [VolstruisGids]:\n> ").strip() or "VolstruisGids"

        # Reasonable events for our checkout flow (Yoco may accept or ignore)
        # Common ones seen in examples: checkout.paid, payment.succeeded, etc.
        # You can experiment; many setups use a wildcard or specific list.
        events = ["checkout.paid", "payment.succeeded", "checkout.completed"]

        print(f"\nRegistering webhook...")
        print(f"  URL:  {url}")
        print(f"  Name: {name}")
        print(f"  Events (suggested): {events}")
        print()

        try:
            result = client.register_webhook(url, name=name, events=events)
            print("\n--- Registration complete ---")
            print("Copy any 'secret' / signing secret value that was returned and put it in .env:")
            print("  YOCO_WEBHOOK_SECRET=the_value_here")
            print("\nThen fully restart your Flask server.")
            print("After that, test a real (non-mock) credit purchase.")
            print("\nTo list webhooks later: python register_yoco_webhook.py list")
        except Exception as e:
            print("\nRegistration failed. See error above.")
            print("Common reasons:")
            print("  - Using a placeholder/mock key instead of a real sk_test_... key")
            print("  - The URL is not publicly reachable from the internet (use ngrok)")
            print("  - Yoco requires specific event names or additional fields for your account")
            print("  - Online Payments / Payment Gateway not yet enabled on this Yoco account")
            print("\nTry creating the webhook from the Yoco Business Portal UI under:")
            print("  Selling Online → Payment Gateway → Webhooks (if available)")


if __name__ == "__main__":
    main()
