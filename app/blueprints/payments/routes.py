from flask import Blueprint, render_template, redirect, url_for, request, jsonify, current_app, flash
from flask_login import login_required, current_user
from app import db
from app.models.payment import Payment
from app.models.credit_transaction import CreditTransaction
from app.models.promotion import Promotion
from app.models.listing import Listing
from app.utils.yoco_client import YocoClient
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

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

        client = YocoClient()
        checkout = client.create_checkout(
            amount_cents=amount_cents,
            success_url=success_url,
            cancel_url=cancel_url,
            failure_url=failure_url,
            metadata=metadata,
            description=description
        )

        yoco_checkout_id = checkout['id']

        # Record in DB - prefer CreditTransaction for credits, Payment for promotions
        if credits > 0 or package_id:
            txn = CreditTransaction(
                user_id=current_user.id,
                amount=credits,
                transaction_type='purchase',
                reference=yoco_checkout_id,
                # status field may be added via migration; default handling below
            )
            # If your CreditTransaction has status (recommended):
            if hasattr(txn, 'status'):
                txn.status = 'pending'
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
                'redirect_url': checkout['redirect_url'],
                'checkout_id': yoco_checkout_id
            })
        else:
            # Form post from buy-credits → redirect user to Yoco
            return redirect(checkout['redirect_url'])

    except Exception as e:
        logger.error(f"Yoco create_checkout error: {str(e)}")
        db.session.rollback()
        if request.is_json:
            return jsonify({'error': 'Failed to create checkout. Please try again.'}), 500
        flash('Failed to start payment. Please try again.', 'danger')
        return redirect(url_for('profile.buy_credits'))


@payments_bp.route('/payment-success')
@login_required
def payment_success():
    """Yoco success redirect handler (user is redirected here after successful payment)"""
    checkout_id = request.args.get('checkoutId') or request.args.get('id')
    flash('Payment successful! Your credits/promotion will be activated shortly.', 'success')
    
    # For credits flow
    if current_user.is_authenticated:
        return redirect(url_for('profile.buy_credits'))
    return redirect(url_for('main.index'))


@payments_bp.route('/payment-cancel')
@login_required
def payment_cancel():
    """Yoco cancel/failure handler"""
    flash('Payment was cancelled or failed.', 'info')
    return redirect(url_for('profile.buy_credits'))


@payments_bp.route('/yoco-webhook', methods=['POST'])
def yoco_webhook():
    """
    Yoco Webhook handler.
    Endpoint: https://yourdomain.com/payments/yoco-webhook
    Configure this URL in your Yoco Dashboard → Webhooks.
    """
    signature = request.headers.get('x-yoco-signature') or request.headers.get('X-Yoco-Signature')
    payload = request.get_data()

    client = YocoClient()
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
        txn = CreditTransaction.query.filter_by(reference=checkout_id).first()
        if txn and status in ('paid', 'successful', 'complete'):
            if getattr(txn, 'status', 'pending') != 'success':
                credits = txn.amount
                from app.models.user import User
                user = User.query.get(txn.user_id)

                if user and credits > 0:
                    user.credit_balance = (user.credit_balance or 0) + credits
                    if hasattr(txn, 'status'):
                        txn.status = 'success'
                    db.session.commit()
                    logger.info(f"Credits added via Yoco webhook: {credits} to user {txn.user_id}")

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
    listing = Listing.query.get_or_404(listing_id)
    if listing.user_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('main.index'))

    packages = [
        {'name': 'Basic Boost', 'price': 99, 'days': 7, 'description': 'Top placement for 7 days', 'id': 'basic'},
        {'name': 'Premium Boost', 'price': 199, 'days': 14, 'description': 'Top placement + badge for 14 days', 'id': 'premium'}
    ]
    return render_template('payments/promote.html', listing=listing, packages=packages)


# Note: For direct boost from listing_detail, use a form that POSTs to /payments/create-checkout
# with listing_id and amount/credits. See updated listing_detail.html example.