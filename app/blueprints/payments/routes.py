from flask import Blueprint, render_template, redirect, url_for, request, jsonify, current_app, flash
from flask_login import login_required, current_user
from app import db
from app.models.payment import Payment
from app.models.credit_transaction import CreditTransaction
from app.models.payment_transaction import PaymentTransaction
from app.models.promotion import Promotion
from app.models.listing import Listing
from app.utils.yoco import YocoClient  # new clean client: respects YOCO_TEST_MODE=false for live keys
from app.utils.yoco_client import YocoClient as LegacyYocoClient  # keep for verify_webhook_signature (webhook + register script)
import json
from datetime import datetime, timedelta
from decimal import Decimal
import logging

# Stripe for spec v1 Credit packs + Monthly subs (Yoco remains for existing credit purchases)
try:
    import stripe
except ImportError:
    stripe = None

logger = logging.getLogger(__name__)

# ============================================================
# STRIPE CREDIT PACKS + BUSINESS MONTHLY (per spec v1)
# ============================================================
CREDIT_PACKS = {
    "pack_5":  {"credits": 5,  "price_zar": 49,  "name": "Starter Pack"},
    "pack_10": {"credits": 10, "price_zar": 89,  "name": "Popular Pack"},
    "pack_25": {"credits": 25, "price_zar": 199, "name": "Power Pack"},
}

# Unlimited Credit Passes (one-time, no recurring) — replaces monthly subscriptions
UNLIMITED_PASSES = {
    "pass_30": {"days": 30, "price_zar": 299, "name": "30-Day Unlimited Pass"},
    "pass_60": {"days": 60, "price_zar": 499, "name": "60-Day Unlimited Pass"},
    "pass_90": {"days": 90, "price_zar": 699, "name": "90-Day Unlimited Pass"},
}

BUSINESS_MONTHLY = {
    "price_zar": 149,
    "credits_per_month": 20,
    "features": ["Business badge", "Priority in search", "20 credits/month"]
}

def _init_stripe():
    """Initialize Stripe with current config key. Safe if key missing or stripe not installed."""
    global stripe
    if stripe is None:
        try:
            import stripe as _stripe
            stripe = _stripe
        except ImportError:
            return False
    sk = current_app.config.get('STRIPE_SECRET_KEY') or current_app.config.get('STRIPE_API_KEY')
    if sk:
        stripe.api_key = sk
    return bool(sk)


def _handle_successful_stripe_payment(session):
    """Fulfill credits from Stripe Checkout session (one-time or sub checkout).
    Idempotent using stripe_session_id lookup.
    """
    session_id = session.get('id')
    metadata = session.get('metadata') or {}
    user_id = metadata.get('user_id')
    pack_id = metadata.get('pack_id')
    credits = metadata.get('credits')
    sub_type = metadata.get('type')  # 'credits' or 'business_monthly'

    if not user_id:
        logger.warning("Stripe session missing user_id in metadata")
        return

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        logger.warning(f"Invalid user_id in Stripe metadata: {user_id}")
        return

    from app.models.user import User
    user = User.query.get(user_id)
    if not user:
        logger.warning(f"User {user_id} not found for Stripe session {session_id}")
        return

    # Find or create PaymentTransaction record
    txn = PaymentTransaction.query.filter_by(stripe_session_id=session_id).first()
    if not txn:
        # Create if webhook arrived first or direct
        try:
            credits_dec = Decimal(str(credits)) if credits else Decimal('0')
            amount = Decimal(str(session.get('amount_total', 0))) / Decimal('100') if session.get('amount_total') else Decimal('0')
            txn = PaymentTransaction(
                user_id=user_id,
                amount=amount,
                credits_added=credits_dec,
                stripe_session_id=session_id,
                stripe_payment_intent=session.get('payment_intent'),
                status='pending'
            )
            db.session.add(txn)
            db.session.commit()
        except Exception:
            db.session.rollback()
            txn = PaymentTransaction.query.filter_by(stripe_session_id=session_id).first()

    if not txn or getattr(txn, 'status', None) == 'succeeded':
        return

    # Determine credits to add
    credits_to_add = Decimal('0')
    if pack_id and pack_id in CREDIT_PACKS:
        credits_to_add = Decimal(str(CREDIT_PACKS[pack_id]['credits']))
    elif credits:
        credits_to_add = Decimal(str(credits))
    elif sub_type == 'business_monthly':
        credits_to_add = Decimal(str(BUSINESS_MONTHLY['credits_per_month']))

    if credits_to_add > 0:
        user.credit_balance = (user.credit_balance or Decimal('0')) + credits_to_add
        # Also support .credits property
        try:
            user.credits = (user.credits or Decimal('0')) + credits_to_add
        except Exception:
            pass

    txn.status = 'succeeded'
    txn.credits_added = credits_to_add if credits_to_add > 0 else txn.credits_added

    # Handle subscription activation if present
    if session.get('mode') == 'subscription' or sub_type == 'business_monthly':
        sub = session.get('subscription')
        if isinstance(sub, str):
            user.stripe_subscription_id = sub
        cust = session.get('customer')
        if isinstance(cust, str):
            user.stripe_customer_id = cust
        user.is_business = True
        user.subscription_status = 'active'
        user.subscription_type = 'business_monthly'
        # period end will be set from subscription.updated webhook ideally

    db.session.commit()
    logger.info(f"Stripe payment fulfilled: +{credits_to_add} credits to user {user_id} (session {session_id})")


def _fulfill_credit_purchase(checkout_id, raw_yoco_response=None):
    """
    Idempotent credit grant for a Yoco (or mock) checkout.
    Returns number of credits granted (0 if already granted or not found).
    Safe to call from success redirect and from webhook.
    raw_yoco_response: optional full Yoco response (dict or str) to store for debugging.
    """
    if not checkout_id:
        return 0
    txn = CreditTransaction.query.filter_by(reference=checkout_id).first()
    if txn:
        logger.info(f"_fulfill: txn found ref={txn.reference} type={txn.transaction_type} amount={txn.amount} status={getattr(txn, 'status', None)}")
    else:
        logger.warning(f"_fulfill: no CreditTransaction found for reference={checkout_id}")
        return 0

    if not txn or txn.transaction_type != 'purchase' or (txn.amount or 0) <= 0:
        return 0
    status = getattr(txn, 'status', None)
    if status in ('success', 'cancelled', 'failed', 'cancel'):
        # still store raw response if provided and not already set (for debugging)
        if raw_yoco_response and not getattr(txn, 'raw_yoco_response', None):
            try:
                txn.raw_yoco_response = json.dumps(raw_yoco_response) if isinstance(raw_yoco_response, (dict, list)) else str(raw_yoco_response)
                db.session.commit()
            except Exception:
                pass
        return 0
    from app.models.user import User
    user = User.query.get(txn.user_id)
    if not user:
        return 0
    credits = txn.amount or Decimal('0')
    old_balance = user.credit_balance or user.credits or Decimal('0')
    new_balance = old_balance + credits
    # Explicitly update both columns for maximum compatibility with display code
    # (some templates use .credits, some .credit_balance; setter also does this but be defensive)
    user.credit_balance = new_balance
    try:
        user.credits = new_balance
    except Exception:
        pass
    try:
        user.set_credits(new_balance)
    except Exception:
        user.credit_balance = new_balance
        try:
            user.__dict__['credits'] = new_balance
        except Exception:
            pass
    if hasattr(txn, 'status'):
        try:
            txn.status = 'success'
        except Exception:
            pass
    # Store the full Yoco response if provided (for reliability/debug when Yoco responses vary)
    if raw_yoco_response:
        try:
            if isinstance(raw_yoco_response, (dict, list)):
                txn.raw_yoco_response = json.dumps(raw_yoco_response)
            else:
                txn.raw_yoco_response = str(raw_yoco_response)
        except Exception:
            pass
    db.session.commit()
    logger.info(f"Credits fulfilled for checkout {checkout_id}: +{credits} (was {old_balance} -> {new_balance}) to user {txn.user_id}")
    return credits


def _fulfill_unlimited_pass(checkout_id, raw_yoco_response=None):
    """
    Idempotent fulfillment for Unlimited Credit Pass purchases.
    Creates or activates a UserCreditPass for the buyer.
    Safe to call from success redirect + webhook.
    """
    from app.models.user import User
    from app.models.user_credit_pass import UserCreditPass
    from app.models.payment import Payment
    from datetime import datetime, timedelta

    if not checkout_id:
        return False

    # Prefer Payment record (we stored passes there)
    payment = Payment.query.filter_by(yoco_checkout_id=checkout_id).first()
    if payment:
        if payment.status == 'success':
            # already fulfilled
            return True
        user = User.query.get(payment.user_id)
        if not user:
            return False

        # Determine pass details (best effort from amount or we can store in future)
        # For now, match by price (robust enough for our 3 tiers)
        price = payment.amount or 0
        pass_info = None
        for pid, info in UNLIMITED_PASSES.items():
            if abs(float(info['price_zar']) - float(price)) < 0.01:
                pass_info = (pid, info)
                break
        if not pass_info:
            # fallback: default to 30 day if unknown amount
            pass_info = ('pass_30', UNLIMITED_PASSES['pass_30'])

        pid, info = pass_info
        days = info['days']
        now = datetime.utcnow()

        # Check if we already created a pass for this checkout
        existing = UserCreditPass.query.filter_by(yoco_checkout_id=checkout_id).first()
        if existing:
            existing.payment_status = 'success'
            existing.starts_at = existing.starts_at or now
            existing.expires_at = existing.expires_at or (now + timedelta(days=days))
            payment.status = 'success'
            db.session.commit()
            return True

        new_pass = UserCreditPass(
            user_id=user.id,
            pass_type=pid,
            duration_days=days,
            starts_at=now,
            expires_at=now + timedelta(days=days),
            amount_paid=Decimal(str(price)),
            currency='ZAR',
            yoco_checkout_id=checkout_id,
            payment_status='success'
        )
        db.session.add(new_pass)
        payment.status = 'success'
        payment.yoco_status = 'paid'
        db.session.commit()
        logger.info(f"Unlimited Pass fulfilled: {pid} for user {user.id} until {new_pass.expires_at}")
        return True

    # Fallback: try to use a recent txn or metadata path (success handler may create txn)
    # For robustness, also try CreditTransaction path (amount not used for pass)
    txn = CreditTransaction.query.filter_by(reference=checkout_id).first()
    if txn and txn.transaction_type in ('purchase', 'unlimited_pass'):
        user = User.query.get(txn.user_id)
        if user:
            # We don't have exact days here without metadata; assume 30 day fallback
            # (UI-driven purchases will have gone through Payment path above)
            now = datetime.utcnow()
            existing = UserCreditPass.query.filter_by(yoco_checkout_id=checkout_id).first()
            if not existing:
                new_pass = UserCreditPass(
                    user_id=user.id,
                    pass_type='pass_30',
                    duration_days=30,
                    starts_at=now,
                    expires_at=now + timedelta(days=30),
                    amount_paid=Decimal('299'),
                    yoco_checkout_id=checkout_id,
                    payment_status='success'
                )
                db.session.add(new_pass)
            if hasattr(txn, 'status'):
                txn.status = 'success'
            db.session.commit()
            return True
    return False


# Import the blueprint object defined in the package __init__.py
# so that all @payments_bp.route decorators attach to the *registered* blueprint.
from . import payments_bp

@payments_bp.route('/buy-credits')
@login_required
def buy_credits():
    """Dedicated Buy Credits page powered by Yoco Checkout (replaces old modal).
    Credits are only added on confirmed success (via payment_success redirect or webhook).
    """
    personal_packages = [
        {"id": "single", "name": "Single Credit", "credits": 1, "price": 10, "note": "Try it out"},
        {"id": "small", "name": "Small", "credits": 5, "price": 55, "note": "Easy entry"},
        {"id": "standard", "name": "Standard", "credits": 10, "price": 99, "note": "Best value for personal"},
    ]

    business_packages = [
        {"id": "starter", "name": "Starter", "credits": 25, "price": 225, "note": "Light", "level": "Light"},
        {"id": "growth", "name": "Growth", "credits": 50, "price": 420, "note": "Medium", "level": "Medium"},
        {"id": "pro", "name": "Pro", "credits": 100, "price": 790, "note": "Good", "level": "Good"},
        {"id": "enterprise", "name": "Enterprise", "credits": 250, "price": 1750, "note": "Best", "level": "Best"},
    ]

    is_business = current_user.is_business_account
    packages = business_packages if is_business else personal_packages
    max_note = ("Business accounts enjoy volume discounts and higher limits."
                if is_business else
                "Personal accounts: maximum 10 credits per purchase (v1).")

    current_balance = current_user.credits  # use property for consistent display (syncs balance + credits col)
    account_type_label = 'Business' if is_business else 'Personal'

    return render_template(
        'payments/buy_credits.html',
        packages=packages,
        current_balance=current_balance,
        is_business=is_business,
        account_type_label=account_type_label,
        max_note=max_note
    )

# ============================================================
# YOCO CHECKOUT INTEGRATION (Paystack fully removed)
# ============================================================

@payments_bp.route('/create-checkout', methods=['POST'])
@login_required
def create_checkout():
    """
    Unified Yoco Checkout creator for:
    - Credit purchases (from /profile/buy-credits)
    - Listing promotions/boosts
    """
    try:
        # Support both form (buy-credits) and JSON (AJAX from detail page)
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        listing_id = data.get('listing_id')
        package_id = data.get('package_id')
        amount = float(data.get('amount', 0))
        credits = Decimal(str(data.get('credits', 0) or 0))
        description = data.get('description', 'VolstruisGids Purchase')

        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400

        amount_cents = int(amount * 100)

        # Build metadata for webhook/fulfillment
        is_pass = bool(package_id and package_id.startswith('pass_'))
        metadata = {
            'user_id': current_user.id,
            'email': current_user.email or current_user.username,
            'type': 'unlimited_pass' if is_pass else ('credits' if package_id or credits else 'promotion'),
            'listing_id': listing_id,
            'package_id': package_id,
            'credits': credits,
            'pass_type': package_id if is_pass else None,
            'description': description
        }

        # Success/Cancel URLs (adjust as needed for your flow)
        # Force https in production - critical for Yoco live checkouts (many hosts like PythonAnywhere default to http in url_for)
        is_prod = current_app.config.get('FLASK_ENV') == 'production'
        url_scheme = 'https' if is_prod else None
        success_url = url_for('payments.payment_success', _external=True, _scheme=url_scheme)
        cancel_url = url_for('payments.payment_cancel', _external=True, _scheme=url_scheme)
        failure_url = url_for('payments.payment_cancel', _external=True, _scheme=url_scheme)

        # Always log safe key prefix (critical for live key troubleshooting on production deploys)
        cfg_key = current_app.config.get('YOCO_SECRET_KEY')
        key_info = (cfg_key[:12] + '... (len=' + str(len(cfg_key)) + ')') if cfg_key else 'None'
        mode = 'LIVE' if (cfg_key or '').startswith('sk_live_') else 'TEST/MOCK'
        logger.info(f"Yoco create_checkout using {mode} key: {key_info} (FLASK_ENV={current_app.config.get('FLASK_ENV')}, TEST_MODE={current_app.config.get('YOCO_TEST_MODE')})")
        if current_app.config.get('FLASK_ENV') == 'development':
            print(f"DEBUG: About to call Yoco with key {key_info} ({mode})")

        yoco_secret = current_app.config.get('YOCO_SECRET_KEY')
        # If using the known placeholder key from this dev setup, simulate success to allow testing the full flow
        # (real key from Yoco dashboard will do the actual API call)
        if yoco_secret and '5e86cc39lVRK8mgb4d14790af205' in yoco_secret:
            logger.warning("MOCK MODE: Using placeholder Yoco key - simulating successful checkout creation for dev/testing")
            mock_checkout_id = f"chk_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Runtime safety: some dev DBs are missing columns on payments table
            # (listing_id for promotions/passes, yoco fields etc.)
            try:
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    for col in [
                        "listing_id INTEGER NULL",
                        "yoco_checkout_id VARCHAR(100) NULL",
                        "yoco_status VARCHAR(50) NULL",
                        "updated_at DATETIME NULL",
                    ]:
                        try:
                            conn.execute(text(f"ALTER TABLE payments ADD COLUMN {col}"))
                        except Exception:
                            pass  # column already there or other benign error
                    conn.commit()
            except Exception:
                pass  # already exists or other benign error

            # Record in DB same as real path
            if is_pass:
                payment = Payment(
                    user_id=current_user.id,
                    listing_id=None,
                    amount=amount,
                    currency='ZAR',
                    payment_method='yoco',
                    status='pending',
                    transaction_id=None,
                    yoco_checkout_id=mock_checkout_id,
                    yoco_status='created'
                )
                db.session.add(payment)
            elif credits > 0 or package_id:
                txn = CreditTransaction(
                    user_id=current_user.id,
                    amount=credits,
                    transaction_type='purchase',
                    reference=mock_checkout_id,
                )
                if hasattr(txn, 'status'):
                    try:
                        txn.status = 'pending'
                    except Exception:
                        pass
                # mock "response" for completeness
                try:
                    txn.raw_yoco_response = json.dumps({'id': mock_checkout_id, 'status': 'mock_created'})
                except Exception:
                    pass
                db.session.add(txn)
            else:
                payment = Payment(
                    user_id=current_user.id,
                    listing_id=listing_id,
                    amount=amount,
                    currency='ZAR',
                    payment_method='yoco',
                    status='pending',
                    transaction_id=None,
                    yoco_checkout_id=mock_checkout_id,
                    yoco_status='created'
                )
                db.session.add(payment)
            db.session.commit()
            # No test flash — success handler will show the clean "credits added" message
            # Redirect to success handler with the id so it can fulfill (credits added there)
            return redirect(url_for('payments.payment_success', checkoutId=mock_checkout_id))

        client = YocoClient()
        checkout = client.create_checkout(
            amount=amount_cents,
            currency="ZAR",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
        )

        # New client returns raw Yoco response (camelCase keys)
        yoco_checkout_id = checkout.get('id')
        redirect_url = checkout.get('redirectUrl') or checkout.get('redirect_url')

        if not yoco_checkout_id or not redirect_url:
            logger.error(f"Invalid Yoco checkout response (missing id or redirectUrl): {checkout}")
            raise Exception("Yoco did not return a valid redirect URL. Check your live account settings.")

        # Record pending transaction (best-effort in prod; webhook + success handler are authoritative)
        try:
            if is_pass:
                # Runtime safety for dev DBs missing columns on payments table
                try:
                    from sqlalchemy import text
                    with db.engine.connect() as conn:
                        for col in [
                            "listing_id INTEGER NULL",
                            "yoco_checkout_id VARCHAR(100) NULL",
                            "yoco_status VARCHAR(50) NULL",
                            "updated_at DATETIME NULL",
                        ]:
                            try:
                                conn.execute(text(f"ALTER TABLE payments ADD COLUMN {col}"))
                            except Exception:
                                pass
                        conn.commit()
                except Exception:
                    pass

                # One-time Unlimited Pass purchase (no credits added, will create UserCreditPass on fulfill)
                payment = Payment(
                    user_id=current_user.id,
                    listing_id=None,
                    amount=amount,
                    currency='ZAR',
                    payment_method='yoco',
                    status='pending',
                    transaction_id=None,
                    yoco_checkout_id=yoco_checkout_id,
                    yoco_status='created'
                )
                db.session.add(payment)
            elif credits > 0 or package_id:
                txn = CreditTransaction(
                    user_id=current_user.id,
                    amount=credits,
                    transaction_type='purchase',
                    reference=yoco_checkout_id,
                )
                if hasattr(txn, 'status'):
                    try:
                        txn.status = 'pending'
                    except Exception:
                        pass
                # Store the initial Yoco create response (raw) for debugging
                try:
                    txn.raw_yoco_response = json.dumps(checkout)
                except Exception:
                    pass
                db.session.add(txn)
            else:
                # Promotion / listing boost
                payment = Payment(
                    user_id=current_user.id,
                    listing_id=listing_id,
                    amount=amount,
                    currency='ZAR',
                    payment_method='yoco',
                    status='pending',
                    transaction_id=None,
                    yoco_checkout_id=yoco_checkout_id,
                    yoco_status='created'
                )
                db.session.add(payment)
            db.session.commit()
            logger.info(f"Yoco checkout created for user {current_user.id}: {yoco_checkout_id}")
        except Exception as db_err:
            logger.error(f"DB record after successful Yoco checkout failed (user will still be sent to pay; rely on webhook): {db_err}")
            db.session.rollback()

        if request.is_json:
            return jsonify({
                'redirect_url': redirect_url,
                'checkout_id': yoco_checkout_id
            })
        else:
            # Form post from buy-credits → redirect user to Yoco
            # (do this even if our local record had issues)
            return redirect(redirect_url)

    except Exception as e:
        logger.error(f"Yoco create_checkout error: {str(e)}")
        db.session.rollback()
        if request.is_json:
            return jsonify({'error': 'Failed to create checkout. Please try again.'}), 500
        # Give helpful message for common auth issues
        error_msg = str(e)
        if '401' in error_msg or 'Unauthorized' in error_msg:
            key = current_app.config.get('YOCO_SECRET_KEY')
            key_info = (key[:12] + '...' if key else 'None')
            is_live = (key or '').startswith('sk_live_')
            mode_hint = 'LIVE' if is_live else 'TEST'
            hint = ('For LIVE keys: confirm the sk_live_ secret is correct, Online Payments / Checkout is enabled on your Yoco business account, and the key has no extra spaces/quotes. ' if is_live
                    else 'For TEST keys use sk_test_... ')
            flash(f'Payment failed: Invalid or unauthorized Yoco {mode_hint} API key (app using key starting with {key_info}). {hint}See Yoco Dashboard > Developers > API Keys (Secret key, not Publishable). Check server logs for full error. Restart after fixing .env.', 'danger')
        else:
            # For live Yoco issues: most common are bad success/cancel URLs (must be public https),
            # account not enabled for live online payments, or network from host.
            # The real error details are in the server logs (search for "Yoco create_checkout error").
            is_live = (current_app.config.get('YOCO_SECRET_KEY') or '').startswith('sk_live_')
            hint = " (Using live key — verify Yoco account has live Checkout enabled + success URLs are public HTTPS.)" if is_live else ""
            flash(f'Failed to start payment with Yoco. Please try again or contact support.{hint} Check server logs for the exact error.', 'danger')
        return redirect(url_for('payments.buy_credits'))


@payments_bp.route('/payment-success')
def payment_success():
    """Yoco success redirect handler (user is redirected here after successful payment).
    Attempts to fulfill credits (or promotions) using the checkoutId so that
    mock/dev flows and real Yoco redirects result in immediate credit allocation.
    Falls back to the most recent pending purchase txn for the logged-in user
    (in case Yoco does not append the checkout id to the success redirect).
    Webhook is still authoritative for server-confirmed payments.
    """
    args = request.args
    checkout_id = None
    for key in ('checkoutId', 'id', 'checkout_id', 'checkoutid'):
        if key in args:
            checkout_id = args.get(key)
            break
    if not checkout_id and args:
        # Fallback: take first value that looks like a Yoco checkout id
        for val in args.values():
            val = str(val)
            if val and (val.startswith(('ch_', 'chk_', 'CH_')) or len(val) > 10):
                checkout_id = val
                break

    logger.info(f"payment_success received args={dict(args)}, extracted_checkout_id={checkout_id}")

    granted = 0

    # Preferred path for simplicity: Ask the gateway "was this checkout a success?" + read credits + user from the metadata we originally attached.
    # Then ensure a CreditTransaction record exists and let the normal (idempotent) fulfill path do the actual add.
    # This is the closest to "if Yoco reports success, add the credits".
    if checkout_id:
        try:
            yoco = YocoClient()
            ch = yoco.get_checkout(checkout_id)
            if ch:
                ch_status = str(ch.get('status') or ch.get('paymentStatus') or '').lower()
                if ch_status in ('paid', 'successful', 'complete', 'succeeded', 'paid_out'):
                    meta = ch.get('metadata') or {}
                    w_user = meta.get('user_id')
                    w_cr = Decimal(str(meta.get('credits') or 0))
                    if w_user and w_cr > 0:
                        # Make sure the history/fulfillment record exists (lazy creation). Then use the existing guard logic.
                        txn = CreditTransaction.query.filter_by(reference=checkout_id).first()
                        if not txn:
                            txn = CreditTransaction(
                                user_id=int(w_user),
                                amount=w_cr,
                                transaction_type='purchase',
                                reference=checkout_id,
                            )
                            if hasattr(txn, 'status'):
                                txn.status = 'pending'  # will be flipped by fulfill
                            db.session.add(txn)
                            db.session.commit()
                        # Now let the standard idempotent path do the add + status flip + balance update.
                        # Pass the full Yoco response so we store it on the txn.
                        granted = _fulfill_credit_purchase(checkout_id, raw_yoco_response=ch)
                        if granted > 0:
                            logger.info(f"Credits added via verified Yoco checkout (status={ch_status}): +{granted}")
        except Exception as yoco_err:
            logger.warning(f"Yoco get_checkout verification in success failed (falling back): {yoco_err}")

    # Fallback to local txn lookup if gateway verify path didn't result in a grant.
    if granted <= 0 and checkout_id:
        granted = _fulfill_credit_purchase(checkout_id)  # raw response not available here, but txn may already have it from previous attempts

    # Unlimited Pass fulfillment (idempotent)
    if checkout_id:
        try:
            _fulfill_unlimited_pass(checkout_id)
        except Exception as pass_err:
            logger.warning(f"Pass fulfill in success failed (non-fatal): {pass_err}")

    # Last resort: most recent pending purchase for the logged-in user (covers when Yoco redirect has no usable id at all)
    if granted <= 0 and current_user.is_authenticated:
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=45)
            recent_txn = (
                CreditTransaction.query
                .filter(
                    CreditTransaction.user_id == current_user.id,
                    CreditTransaction.transaction_type == 'purchase',
                    CreditTransaction.created_at >= cutoff,
                )
                .order_by(CreditTransaction.created_at.desc())
                .first()
            )
            if recent_txn:
                rstatus = getattr(recent_txn, 'status', None)
                if rstatus not in ('success', 'cancelled', 'failed', 'cancel') and (recent_txn.amount or 0) > 0:
                    granted = _fulfill_credit_purchase(recent_txn.reference)
                    if granted > 0:
                        logger.info(f"payment_success used recent-pending txn fallback for user {current_user.id}")
        except Exception as fb_err:
            logger.warning(f"payment_success recent txn fallback error: {fb_err}")

    if granted > 0:
        flash(f'✅ Payment successful! {granted} credits have been added to your account.', 'success')
    else:
        # Check if it was a pass purchase (via recent Payment)
        was_pass = False
        if checkout_id:
            p = Payment.query.filter_by(yoco_checkout_id=checkout_id).first()
            if p and not p.listing_id:
                was_pass = True
        if was_pass:
            flash('✅ Payment successful! Your Unlimited Credit Pass is now active.', 'success')
        else:
            flash('Payment successful! Your credits/promotion will be activated shortly.', 'success')

    return redirect(url_for('payments.buy_credits'))


@payments_bp.route('/payment-cancel')
def payment_cancel():
    """Yoco cancel/failure handler.
    Extract checkout id if provided by Yoco and mark the txn as cancelled
    so that auto-claim logic and fallbacks do not add credits.
    """
    # Extract checkout id similarly to success (Yoco may append id/checkoutId etc on cancel)
    args = request.args
    checkout_id = None
    for key in ('checkoutId', 'id', 'checkout_id', 'checkoutid'):
        if key in args:
            checkout_id = args.get(key)
            break
    if not checkout_id and args:
        for val in args.values():
            val = str(val)
            if val and (val.startswith(('ch_', 'chk_', 'CH_')) or len(val) > 10):
                checkout_id = val
                break

    if checkout_id:
        try:
            txn = CreditTransaction.query.filter_by(reference=checkout_id).first()
            if txn and getattr(txn, 'status', None) != 'success':
                if hasattr(txn, 'status'):
                    txn.status = 'cancelled'
                db.session.commit()
                logger.info(f"Marked txn {checkout_id} as cancelled (user cancelled on Yoco)")
        except Exception as e:
            logger.warning(f"Error marking cancel for {checkout_id}: {e}")

    flash('Payment was cancelled or failed.', 'info')
    return redirect(url_for('payments.buy_credits'))


@payments_bp.route('/yoco-webhook', methods=['POST'])
def yoco_webhook():
    """
    Yoco Webhook handler.
    Endpoint: https://yourdomain.com/payments/yoco-webhook
    Configure this URL in your Yoco Dashboard → Webhooks.
    Supports both legacy Yoco sig and modern Checkout API (webhook-id/timestamp/signature + whsec base64).
    """
    payload = request.get_data()
    raw_sig = (
        request.headers.get('webhook-signature')
        or request.headers.get('Webhook-Signature')
        or request.headers.get('x-yoco-signature')
        or request.headers.get('X-Yoco-Signature')
    )
    wh_id = request.headers.get('webhook-id') or request.headers.get('Webhook-Id')
    wh_ts = request.headers.get('webhook-timestamp') or request.headers.get('Webhook-Timestamp')

    verified = False
    webhook_secret = current_app.config.get('YOCO_WEBHOOK_SECRET')

    # Try modern Checkout API / Standard Webhooks format first (used with payments.yoco.com)
    if wh_id and wh_ts and raw_sig and webhook_secret and 'whsec_' in str(webhook_secret):
        try:
            import base64
            import hmac as _hmac
            import hashlib as _hashlib
            # secret after whsec_ , base64 decode
            secret_b64 = webhook_secret.split('_', 1)[1] if '_' in webhook_secret else webhook_secret
            secret_bytes = base64.b64decode(secret_b64)
            signed_content = f"{wh_id}.{wh_ts}.".encode() + payload
            computed = base64.b64encode(
                _hmac.new(secret_bytes, signed_content, _hashlib.sha256).digest()
            ).decode()
            # raw_sig may be "v1,xxx v2,yyy" or similar; take first sig part after comma or =
            provided = raw_sig
            if ' ' in provided:
                provided = provided.split()[0]
            if ',' in provided:
                provided = provided.split(',')[-1]
            if '=' in provided:
                provided = provided.split('=')[-1]
            provided = provided.strip()
            if _hmac.compare_digest(computed, provided):
                verified = True
        except Exception as ve:
            logger.warning(f"Modern webhook sig verify error (will try legacy): {ve}")

    if not verified:
        # Fallback to legacy/old Yoco signature (hex on payload only)
        client = LegacyYocoClient()
        if client.verify_webhook_signature(payload, raw_sig):
            verified = True

    if not verified:
        logger.warning("Invalid Yoco webhook signature")
        return jsonify({'status': 'invalid signature'}), 400

    try:
        event = json.loads(payload)
        event_type = event.get('type') or event.get('event')
        data = event.get('data', {}) or event.get('object', {}) or {}

        checkout_id = data.get('id') or data.get('checkoutId') or data.get('checkout_id')
        # Per Yoco Checkout webhook docs: checkoutId may be inside metadata (our echoed metadata or Yoco's)
        if not checkout_id:
            meta = (data.get('metadata') or event.get('metadata') or {})
            checkout_id = meta.get('checkoutId') or meta.get('id') or meta.get('checkout_id')
        status = data.get('status') or data.get('paymentStatus') or data.get('state')

        if not checkout_id:
            return jsonify({'status': 'ignored'}), 200

        logger.info(f"Received Yoco webhook: {event_type} for {checkout_id} - {status} (data keys: {list(data.keys()) if isinstance(data, dict) else 'n/a'})")

        # === Handle Credit Purchase ===
        # Prefer reading directly from the webhook payload / metadata when possible ("if Yoco says success, add the credits it recorded")
        is_paid = (
            status in ('paid', 'successful', 'complete', 'succeeded')
            or (event_type and any(k in str(event_type).lower() for k in ('paid', 'succeeded', 'complete')))
        )
        if is_paid:
            granted = 0
            # Try direct from this event's data (Yoco often echoes the metadata we sent)
            try:
                meta = data.get('metadata') or event.get('metadata') or {}
                w_user_id = meta.get('user_id')
                w_credits = Decimal(str(meta.get('credits') or 0))
                if w_user_id and w_credits > 0:
                    from app.models.user import User
                    usr = User.query.get(int(w_user_id))
                    if usr:
                        old = (usr.credit_balance or usr.credits or Decimal('0'))
                        usr.credits = old + w_credits
                        # record for history (create if the pre-row wasn't there)
                        txn = CreditTransaction.query.filter_by(reference=checkout_id).first() if checkout_id else None
                        if not txn and checkout_id:
                            txn = CreditTransaction(
                                user_id=int(w_user_id),
                                amount=w_credits,
                                transaction_type='purchase',
                                reference=checkout_id,
                            )
                            if hasattr(txn, 'status'):
                                txn.status = 'success'
                            # store full event for debugging Yoco response variations
                            try:
                                txn.raw_yoco_response = json.dumps(event)
                            except Exception:
                                pass
                            db.session.add(txn)
                        elif txn and hasattr(txn, 'status'):
                            txn.status = 'success'
                            if not getattr(txn, 'raw_yoco_response', None):
                                try:
                                    txn.raw_yoco_response = json.dumps(event)
                                except Exception:
                                    pass
                        db.session.commit()
                        granted = w_credits
                        logger.info(f"Credits added directly from webhook metadata: +{granted} to user {w_user_id}")
            except Exception as direct_err:
                logger.warning(f"Direct webhook credit add failed, falling back: {direct_err}")

            if granted <= 0 and checkout_id:
                # pass the raw event data so we can store the full Yoco response
                granted = _fulfill_credit_purchase(checkout_id, raw_yoco_response=event)
            if granted > 0:
                logger.info(f"Credits added via Yoco webhook: {granted} for {checkout_id}")

        # === Handle Unlimited Pass (new one-time passes) ===
        if checkout_id and is_paid:
            try:
                _fulfill_unlimited_pass(checkout_id, raw_yoco_response=event)
            except Exception as p_err:
                logger.warning(f"Pass webhook fulfill error (non-fatal): {p_err}")

        # === Handle Promotion / Listing Boost ===
        payment = Payment.query.filter_by(yoco_checkout_id=checkout_id).first()
        if payment and is_paid:
            if payment.status != 'success':
                payment.status = 'success'
                payment.yoco_status = status
                payment.transaction_id = data.get('paymentId') or data.get('id')
                db.session.commit()

                # Activate promotion (7 days default)
                if payment.listing_id:
                    # Use only fields that exist on the current Promotion model
                    promotion = Promotion.query.filter_by(listing_id=payment.listing_id).first()
                    if not promotion:
                        promotion = Promotion(
                            listing_id=payment.listing_id,
                            start_date=datetime.utcnow(),
                            end_date=datetime.utcnow() + timedelta(days=7),
                            amount_paid=float(payment.amount or 0),
                            payment_status='completed'
                        )
                        db.session.add(promotion)
                        db.session.commit()
                    logger.info(f"Promotion activated for listing {payment.listing_id} via Yoco")

        return jsonify({'status': 'success'}), 200

    except Exception as e:
        logger.error(f"Yoco webhook processing error: {str(e)}")
        # Always return 200 to Yoco so they don't retry spam
        return jsonify({'status': 'error but acknowledged'}), 200


# ============================================================
# Legacy promote route (kept for backward compatibility, now uses Yoco)
# ============================================================

@payments_bp.route('/promote/<int:listing_id>')
@login_required
def promote(listing_id):
    """Legacy promote entry (kept for back-compat). Now routes to the unified Yoco buy-credits flow.
    Direct promotion purchase from listing detail uses POST /payments/create-checkout with listing_id.
    """
    listing = Listing.query.get_or_404(listing_id)
    if listing.user_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.index'))
    flash('Use Buy Credits to purchase a promotion for this listing, or the boost option on the detail page.', 'info')
    return redirect(url_for('payments.buy_credits'))


# Note: For direct boost from listing_detail, use a form that POSTs to /payments/create-checkout
# with listing_id and amount/credits. See updated listing_detail.html example.


# ============================================================
# STRIPE INTEGRATION ROUTES (Credit packs + Business Monthly Subscription)
# Follows spec v1 closely. Yoco credit flow remains active at /buy-credits
# ============================================================

@payments_bp.route('/billing')
@login_required
def credits_billing():
    """Credits & Billing page — now focused on Yoco credit packs + Unlimited Credit Passes.
    Monthly/recurring subscriptions removed per spec.
    """
    stripe_ready = _init_stripe()

    current_balance = current_user.credit_balance or current_user.credits or Decimal('0')

    is_business = current_user.is_business_account
    sub_status = current_user.subscription_status or 'none'

    # Unlimited Pass status (critical for display + logic)
    has_unlimited = current_user.has_active_unlimited_pass()
    unlimited_until = None
    active_pass = None
    if has_unlimited:
        # find the active one for display
        from app.models.user_credit_pass import UserCreditPass
        from datetime import datetime
        now = datetime.utcnow()
        active_pass = UserCreditPass.query.filter(
            UserCreditPass.user_id == current_user.id,
            UserCreditPass.starts_at <= now,
            UserCreditPass.expires_at >= now
        ).order_by(UserCreditPass.expires_at.desc()).first()
        if active_pass:
            unlimited_until = active_pass.expires_at

    # Last 10 transactions (Stripe + legacy CreditTransaction purchases for display)
    stripe_txns = PaymentTransaction.query.filter_by(user_id=current_user.id).order_by(
        PaymentTransaction.created_at.desc()
    ).limit(10).all()

    # Also pull recent credit purchases for history completeness
    credit_txns = CreditTransaction.query.filter(
        CreditTransaction.user_id == current_user.id,
        CreditTransaction.transaction_type == 'purchase'
    ).order_by(CreditTransaction.created_at.desc()).limit(5).all()

    transactions = []
    for t in stripe_txns:
        transactions.append({
            'date': t.created_at,
            'amount': float(t.amount or 0),
            'credits': float(t.credits_added or 0),
            'status': t.status,
            'provider': 'stripe'
        })
    for t in credit_txns:
        transactions.append({
            'date': t.created_at,
            'amount': None,  # legacy may not store zar amount
            'credits': float(t.amount or 0),
            'status': t.status or 'success',
            'provider': 'yoco'
        })
    # Sort combined desc by date
    transactions.sort(key=lambda x: x['date'] or datetime.min, reverse=True)
    transactions = transactions[:10]

    return render_template(
        'payments/credits_billing.html',
        credit_packs=CREDIT_PACKS,
        unlimited_passes=UNLIMITED_PASSES,
        current_balance=current_balance,
        is_business=is_business,
        subscription_status=sub_status,
        has_unlimited=has_unlimited,
        unlimited_until=unlimited_until,
        transactions=transactions,
        stripe_pk=current_app.config.get('STRIPE_PUBLISHABLE_KEY'),
        stripe_configured=stripe_ready
    )


@payments_bp.route('/buy-credits/<pack_id>', methods=['POST'])
@login_required
def create_credit_checkout(pack_id):
    """Stripe Checkout for one-time credit packs (spec v1)."""
    if not _init_stripe():
        flash('Stripe is not configured for packs/monthly. Credit top-ups use Yoco at Buy Credits. Set Stripe keys only if using business subscription.', 'info')
        return redirect(url_for('payments.credits_billing'))

    pack = CREDIT_PACKS.get(pack_id)
    if not pack:
        flash('Invalid pack selected.', 'danger')
        return redirect(url_for('payments.credits_billing'))

    try:
        success_url = url_for('payments.stripe_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('payments.credits_billing', _external=True)

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'zar',
                    'product_data': {'name': pack['name']},
                    'unit_amount': int(pack['price_zar'] * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=current_user.email,
            metadata={
                'user_id': str(current_user.id),
                'pack_id': pack_id,
                'credits': str(pack['credits']),
                'type': 'credits'
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        logger.error(f"Stripe credit checkout error: {e}")
        flash('Unable to start Stripe checkout. Please try again later.', 'danger')
        return redirect(url_for('payments.credits_billing'))


@payments_bp.route('/subscribe/business', methods=['POST'])
@login_required
def create_business_subscription():
    """Stripe Checkout for monthly business subscription (R149/mo)."""
    if not _init_stripe():
        flash('Stripe not configured for monthly sub. Use Yoco Buy Credits for regular purchases.', 'info')
        return redirect(url_for('payments.credits_billing'))

    try:
        success_url = url_for('payments.stripe_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('payments.credits_billing', _external=True)

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'zar',
                    'product_data': {'name': 'Business Monthly Subscription'},
                    'unit_amount': int(BUSINESS_MONTHLY['price_zar'] * 100),
                    'recurring': {'interval': 'month'},
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=current_user.email,
            metadata={
                'user_id': str(current_user.id),
                'type': 'business_monthly',
                'credits': str(BUSINESS_MONTHLY['credits_per_month'])
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        logger.error(f"Stripe subscription checkout error: {e}")
        flash('Unable to start subscription checkout.', 'danger')
        return redirect(url_for('payments.credits_billing'))


@payments_bp.route('/stripe-success')
@login_required
def stripe_success():
    """Success redirect handler for Stripe (credit pack or subscription).
    Webhook is authoritative; this does best-effort fulfillment.
    """
    session_id = request.args.get('session_id')
    if session_id and _init_stripe() and stripe is not None:
        try:
            session = stripe.checkout.Session.retrieve(session_id, expand=['subscription'])
            _handle_successful_stripe_payment(session)
        except Exception as e:
            logger.error(f"Stripe success retrieve error: {e}")

    flash('✅ Payment successful! Credits (and subscription status if applicable) will be updated shortly.', 'success')
    return redirect(url_for('payments.credits_billing'))


@payments_bp.route('/stripe-cancel')
@login_required
def stripe_cancel():
    flash('Payment cancelled or failed. No charges were made.', 'info')
    return redirect(url_for('payments.credits_billing'))


@payments_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Stripe webhook handler (critical per spec).
    Configure endpoint in Stripe Dashboard: /payments/webhook
    """
    if not _init_stripe() or stripe is None:
        logger.warning("Stripe webhook received but Stripe not configured or installed")
        return 'Stripe not configured', 400

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')

    if not webhook_secret:
        logger.warning("Stripe webhook received but no STRIPE_WEBHOOK_SECRET configured")
        return 'Webhook not configured', 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        logger.error(f"Stripe webhook signature error: {e}")
        return str(e), 400

    event_type = event['type']
    data = event['data']['object']

    logger.info(f"Stripe webhook received: {event_type}")

    if event_type == 'checkout.session.completed':
        _handle_successful_stripe_payment(data)

    elif event_type in ('customer.subscription.created', 'customer.subscription.updated'):
        # Update user subscription status from Stripe sub object
        sub_id = data.get('id')
        cust_id = data.get('customer')
        status = data.get('status')
        current_period_end = data.get('current_period_end')

        if cust_id:
            from app.models.user import User
            user = User.query.filter_by(stripe_customer_id=cust_id).first()
            if not user and sub_id:
                # fallback lookup via subscription id
                user = User.query.filter_by(stripe_subscription_id=sub_id).first()
            if user:
                user.stripe_subscription_id = sub_id
                user.subscription_status = status
                if current_period_end:
                    try:
                        user.subscription_current_period_end = datetime.utcfromtimestamp(int(current_period_end))
                    except Exception:
                        pass
                if status == 'active':
                    user.is_business = True
                    user.subscription_type = 'business_monthly'
                elif status in ('canceled', 'past_due'):
                    # Keep is_business True until end of period for v1 simplicity
                    pass
                db.session.commit()
                logger.info(f"Updated subscription for user {user.id}: {status}")

    elif event_type == 'customer.subscription.deleted':
        sub_id = data.get('id')
        if sub_id:
            from app.models.user import User
            user = User.query.filter_by(stripe_subscription_id=sub_id).first()
            if user:
                user.subscription_status = 'canceled'
                # credits stop renewing; is_business can stay or be toggled - leave as is for v1
                db.session.commit()

    return '', 200
