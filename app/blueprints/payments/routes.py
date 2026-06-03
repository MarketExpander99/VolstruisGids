from flask import Blueprint, render_template, redirect, url_for, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models.payment import Payment
from app.models.promotion import Promotion
from app.models.listing import Listing
from app import db
import requests
import hmac
import hashlib
import json
from datetime import datetime

payments = Blueprint('payments', __name__)  # This is already defined in __init__.py but kept for clarity in routes

@payments.route('/promote/<int:listing_id>')
@login_required
def promote(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    if listing.user_id != current_user.id:
        return redirect(url_for('listings.index'))
    
    # Simple packages for now
    packages = [
        {'name': 'Basic Boost', 'price': 99, 'days': 7, 'description': 'Top placement for 7 days'},
        {'name': 'Premium Boost', 'price': 199, 'days': 14, 'description': 'Top placement + badge for 14 days'}
    ]
    return render_template('payments/promote.html', listing=listing, packages=packages)

@payments.route('/create-payment', methods=['POST'])
@login_required
def create_payment():
    data = request.get_json()
    listing_id = data.get('listing_id')
    package_name = data.get('package_name')
    amount = data.get('amount')
    
    listing = Listing.query.get_or_404(listing_id)
    if listing.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Create pending payment record
    payment = Payment(
        user_id=current_user.id,
        listing_id=listing_id,
        amount=amount,
        payment_method='paystack',
        status='pending',
        reference=f"volstruis_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    )
    db.session.add(payment)
    db.session.commit()
    
    # Initialize Paystack transaction
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json"
    }
    payload = {
        "email": current_user.email,
        "amount": int(amount * 100),  # cents
        "reference": payment.reference,
        "callback_url": url_for('payments.payment_callback', _external=True)
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return jsonify({'authorization_url': data['data']['authorization_url']})
    else:
        return jsonify({'error': 'Payment initialization failed'}), 400

@payments.route('/payment-callback')
def payment_callback():
    reference = request.args.get('reference')
    if not reference:
        return redirect(url_for('main.index'))
    
    # Verify with Paystack
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {current_app.config['PAYSTACK_SECRET_KEY']}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if data['data']['status'] == 'success':
            payment = Payment.query.filter_by(reference=reference).first()
            if payment:
                payment.status = 'success'
                payment.transaction_id = data['data']['id']
                db.session.commit()
                
                # Activate promotion (basic for now)
                promotion = Promotion(
                    listing_id=payment.listing_id,
                    user_id=payment.user_id,
                    payment_id=payment.id,
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow()  # TODO: set proper duration based on package
                )
                db.session.add(promotion)
                db.session.commit()
                
                return redirect(url_for('listings.detail', id=payment.listing_id))
    
    return redirect(url_for('main.index'))

@payments.route('/webhook', methods=['POST'])
def paystack_webhook():
    # Verify signature
    signature = request.headers.get('x-paystack-signature')
    payload = request.get_data()
    
    computed_sig = hmac.new(
        current_app.config['PAYSTACK_SECRET_KEY'].encode(),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    if computed_sig != signature:
        return jsonify({'status': 'invalid signature'}), 400
    
    event = json.loads(payload)
    if event['event'] == 'charge.success':
        reference = event['data']['reference']
        payment = Payment.query.filter_by(reference=reference).first()
        if payment and payment.status == 'pending':
            payment.status = 'success'
            payment.transaction_id = event['data']['id']
            db.session.commit()
            
            # Activate promotion (duplicate logic for webhook reliability)
            promotion = Promotion.query.filter_by(payment_id=payment.id).first()
            if not promotion:
                promotion = Promotion(
                    listing_id=payment.listing_id,
                    user_id=payment.user_id,
                    payment_id=payment.id,
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow()
                )
                db.session.add(promotion)
                db.session.commit()
    
    return jsonify({'status': 'success'}), 200