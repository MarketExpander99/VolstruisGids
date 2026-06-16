from flask import Blueprint, render_template, redirect, url_for, request, jsonify, current_app, flash
from flask_login import login_required, current_user
from app import db
from app.models.payment import Payment
from app.models.credit_transaction import CreditTransaction
from app.models.promotion import Promotion
from app.models.listing import Listing
from app.utils.yoco import YocoClient  # new clean client: respects YOCO_TEST_MODE=false for live keys
from app.utils.yoco_client import YocoClient as LegacyYocoClient  # keep for verify_webhook_signature (webhook + register script)
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


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
    credits = txn.amount
    user.credit_balance = (user.credit_balance or 0) + credits
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

    is_business = current_user.account_type == 'business' or current_user.is_business
    packages = business_packages if is_business else personal_packages
    max_note = ("Business accounts enjoy volume discounts and higher limits."
                if is_business else
                "Personal accounts: maximum 10 credits per purchase (v1).")

    current_balance = current_user.credit_balance or 0
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
        credits = int(data.get('credits', 0))
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