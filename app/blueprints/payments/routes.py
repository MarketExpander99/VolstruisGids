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


def _fulfill_credit_purchase(checkout_id):
    """
    Idempotent credit grant for a Yoco (or mock) checkout.
    Returns number of credits granted (0 if already granted or not found).
    Safe to call from success redirect and from webhook.
    """
    if not checkout_id:
        return 0
    txn = CreditTransaction.query.filter_by(reference=checkout_id).first()
    if not txn or txn.transaction_type != 'purchase' or (txn.amount or 0) <= 0:
        return 0
    if getattr(txn, 'status', None) == 'success':
        return 0
    from app.models.user import User
    user = User.query.get(txn.user_id)
    if not user:
        return 0
    credits = txn.amount or Decimal('0')
    user.credit_balance = (user.credit_balance or Decimal('0')) + credits
    if hasattr(txn, 'status'):
        txn.status = 'success'
    db.session.commit()
    logger.info(f"Credits fulfilled for checkout {checkout_id}: +{credits} to user {txn.user_id}")
    return credits

# Import the blueprint object defined in the package __init__.py
# so that all @payments_bp.route decorators attach to the *registered* blueprint.
from . import payments_bp

@payments_bp.route('/buy-credits')
@login_required
def buy_credits():
    """Dedicated Buy Credits page powered by Yoco Checkout (replaces old modal)."""
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

    current_balance = current_user.credit_balance or Decimal('0')
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
        metadata = {
            'user_id': current_user.id,
            'email': current_user.email or current_user.username,
            'type': 'credits' if package_id or credits else 'promotion',
            'listing_id': listing_id,
            'package_id': package_id,
            'credits': credits,
            'description': description
        }

        # Success/Cancel URLs (adjust as needed for your flow)
        success_url = url_for('payments.payment_success', _external=True)
        cancel_url = url_for('payments.payment_cancel', _external=True)
        failure_url = url_for('payments.payment_cancel', _external=True)

        # Debug what key the app actually has (safe prefix only) — only in development
        if current_app.config.get('FLASK_ENV') == 'development':
            cfg_key = current_app.config.get('YOCO_SECRET_KEY')
            key_info = (cfg_key[:12] + '... (len=' + str(len(cfg_key)) + ')') if cfg_key else 'None'
            print(f"DEBUG: About to call Yoco with key {key_info}, FLASK_ENV=development")
            logger.info(f"DEBUG: About to call Yoco with key {key_info}")

        yoco_secret = current_app.config.get('YOCO_SECRET_KEY')
        # If using the known placeholder key from this dev setup, simulate success to allow testing the full flow
        # (real key from Yoco dashboard will do the actual API call)
        if yoco_secret and '5e86cc39lVRK8mgb4d14790af205' in yoco_secret:
            logger.warning("MOCK MODE: Using placeholder Yoco key - simulating successful checkout creation for dev/testing")
            mock_checkout_id = f"chk_mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            # Record in DB same as real path
            if credits > 0 or package_id:
                txn = CreditTransaction(
                    user_id=current_user.id,
                    amount=credits,
                    transaction_type='purchase',
                    reference=mock_checkout_id,
                    status='pending'
                )
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

        # Record in DB - prefer CreditTransaction for credits, Payment for promotions
        if credits > 0 or package_id:
            txn = CreditTransaction(
                user_id=current_user.id,
                amount=credits,
                transaction_type='purchase',
                reference=yoco_checkout_id,
                status='pending'
            )
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
                yoco_checkout_id=yoco_checkout_id,  # new field
                yoco_status='created'
            )
            db.session.add(payment)

        db.session.commit()

        logger.info(f"Yoco checkout created for user {current_user.id}: {yoco_checkout_id}")

        if request.is_json:
            return jsonify({
                'redirect_url': redirect_url,
                'checkout_id': yoco_checkout_id
            })
        else:
            # Form post from buy-credits → redirect user to Yoco
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
            flash(f'Payment failed: Invalid Yoco API key (app using key starting with {key_info}). Get a real secret key (sk_test_...) from Yoco Dashboard (log in > Developers > API Keys > Secret keys section for test). Replace the full value in .env (no quotes/spaces), set FLASK_ENV=development, fully restart server. See console DEBUG for details.', 'danger')
        else:
            flash('Failed to start payment. Please try again or contact support.', 'danger')
        return redirect(url_for('payments.buy_credits'))


@payments_bp.route('/payment-success')
@login_required
def payment_success():
    """Yoco success redirect handler (user is redirected here after successful payment).
    Attempts to fulfill credits (or promotions) using the checkoutId so that
    mock/dev flows and real Yoco redirects result in immediate credit allocation.
    Webhook is still authoritative for server-confirmed payments.
    """
    checkout_id = request.args.get('checkoutId') or request.args.get('id')
    granted = _fulfill_credit_purchase(checkout_id)

    if granted > 0:
        flash(f'✅ Payment successful! {granted} credits have been added to your account.', 'success')
    else:
        # Could be a promotion or webhook will handle it shortly
        flash('Payment successful! Your credits/promotion will be activated shortly.', 'success')

    return redirect(url_for('payments.buy_credits'))


@payments_bp.route('/payment-cancel')
@login_required
def payment_cancel():
    """Yoco cancel/failure handler"""
    flash('Payment was cancelled or failed.', 'info')
    return redirect(url_for('payments.buy_credits'))


@payments_bp.route('/yoco-webhook', methods=['POST'])
def yoco_webhook():
    """
    Yoco Webhook handler.
    Endpoint: https://yourdomain.com/payments/yoco-webhook
    Configure this URL in your Yoco Dashboard → Webhooks.
    """
    signature = request.headers.get('x-yoco-signature') or request.headers.get('X-Yoco-Signature')
    payload = request.get_data()

    client = LegacyYocoClient()
    if not client.verify_webhook_signature(payload, signature):
        logger.warning("Invalid Yoco webhook signature")
        return jsonify({'status': 'invalid signature'}), 400

    try:
        event = json.loads(payload)
        event_type = event.get('type') or event.get('event')
        data = event.get('data', {}) or event.get('object', {})

        checkout_id = data.get('id') or data.get('checkoutId')
        status = data.get('status') or data.get('paymentStatus')

        if not checkout_id:
            return jsonify({'status': 'ignored'}), 200

        logger.info(f"Received Yoco webhook: {event_type} for {checkout_id} - {status}")

        # === Handle Credit Purchase ===
        if status in ('paid', 'successful', 'complete'):
            granted = _fulfill_credit_purchase(checkout_id)
            if granted > 0:
                logger.info(f"Credits added via Yoco webhook: {granted} for {checkout_id}")

        # === Handle Promotion / Listing Boost ===
        payment = Payment.query.filter_by(yoco_checkout_id=checkout_id).first()
        if payment and status in ('paid', 'successful', 'complete'):
            if payment.status != 'success':
                payment.status = 'success'
                payment.yoco_status = status
                payment.transaction_id = data.get('paymentId') or data.get('id')
                db.session.commit()

                # Activate promotion (7 days default)
                if payment.listing_id:
                    promotion = Promotion.query.filter_by(payment_id=payment.id).first()
                    if not promotion:
                        promotion = Promotion(
                            listing_id=payment.listing_id,
                            user_id=payment.user_id,
                            payment_id=payment.id,
                            start_date=datetime.utcnow(),
                            end_date=datetime.utcnow() + timedelta(days=7)
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
    """Credits & Billing page: Stripe credit packs + monthly business sub + tx history.
    Per spec. Existing Yoco /buy-credits still available.
    """
    _init_stripe()

    current_balance = current_user.credit_balance or current_user.credits or Decimal('0')

    is_business = current_user.is_business_account
    sub_status = current_user.subscription_status or 'none'

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
        business_monthly=BUSINESS_MONTHLY,
        current_balance=current_balance,
        is_business=is_business,
        subscription_status=sub_status,
        transactions=transactions,
        stripe_pk=current_app.config.get('STRIPE_PUBLISHABLE_KEY')
    )


@payments_bp.route('/buy-credits/<pack_id>', methods=['POST'])
@login_required
def create_credit_checkout(pack_id):
    """Stripe Checkout for one-time credit packs (spec v1)."""
    if not _init_stripe():
        flash('Stripe is not configured. Set STRIPE_SECRET_KEY in your environment.', 'danger')
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
        flash('Stripe is not configured. Set STRIPE_SECRET_KEY.', 'danger')
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
