import os
import json
import urllib.request
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.models.listing import Listing
from .forms import ProfileForm
import requests  # for Paystack
from app.blueprints.profile import profile_bp

@profile_bp.route('/buy-credits', methods=['GET', 'POST'])
@login_required
def buy_credits():
    """Buy Credits page - powered by Paystack"""

    personal_packages = [
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

    if request.method == 'POST':
        package_id = request.form.get('package_id')
        selected = next((p for p in packages if p['id'] == package_id), None)

        if not selected:
            flash('Invalid package selected.', 'danger')
            return redirect(url_for('profile.buy_credits'))

        credits_to_add = selected['credits']
        amount = selected['price']

        # Create transaction record (NO status field)
        reference = f"credits_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        txn = CreditTransaction(
            user_id=current_user.id,
            amount=credits_to_add,
            transaction_type='purchase',
            reference=reference
        )
        db.session.add(txn)
        db.session.commit()

               # === PAYSTACK DEBUG VERSION ===
        try:
            secret_key = current_app.config.get('PAYSTACK_SECRET_KEY')
            print("DEBUG - Using secret key:", secret_key[:10] + "..." if secret_key else "None")   # <-- Check this in terminal

            url = "https://api.paystack.co/transaction/initialize"
            headers = {
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "email": current_user.email,
                "amount": int(amount * 100),
                "reference": reference,
                "callback_url": url_for('profile.payment_success', _external=True),
                "metadata": {
                    "user_id": current_user.id,
                    "credits": credits_to_add,
                    "package_id": package_id
                }
            }

            response = requests.post(url, json=payload, headers=headers, timeout=15)
            result = response.json()

            print("DEBUG - Paystack response:", result)   # <-- Very important

            if result.get('status') and result['data'].get('authorization_url'):
                return redirect(result['data']['authorization_url'])
            else:
                flash(f'Paystack error: {result}', 'danger')   # Shows actual error
                return redirect(url_for('profile.buy_credits'))

        except Exception as e:
            print("DEBUG - Exception:", str(e))
            flash(f'Paystack exception: {str(e)}', 'danger')
            return redirect(url_for('profile.buy_credits'))

    # GET request
    return render_template(
        'profile/buy_credits.html',
        packages=packages,
        max_note=max_note,
        current_balance=current_user.credit_balance or 0,
        is_business=is_business,
        account_type_label='Business' if is_business else 'Personal'
    )
    """Buy Credits page - now powered by Paystack"""

    personal_packages = [
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

    if request.method == 'POST':
        package_id = request.form.get('package_id')
        selected = next((p for p in packages if p['id'] == package_id), None)

        if not selected:
            flash('Invalid package selected.', 'danger')
            return redirect(url_for('profile.buy_credits'))

        credits_to_add = selected['credits']
        amount = selected['price']  # in Rands

        # Create a pending credit transaction
        reference = f"credits_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        txn = CreditTransaction(
            user_id=current_user.id,
            amount=credits_to_add,
            transaction_type='purchase',
            reference=reference,
            status='pending'
        )
        db.session.add(txn)
        db.session.commit()

        # === PAYSTACK INTEGRATION ===
        try:
            url = "https://api.paystack.co/transaction/initialize"
            headers = {
                "Authorization": f"Bearer {current_app.config.get('PAYSTACK_SECRET_KEY')}",
                "Content-Type": "application/json"
            }
            payload = {
                "email": current_user.email,
                "amount": int(amount * 100),  # convert to cents
                "reference": reference,
                "callback_url": url_for('profile.payment_success', _external=True),
                "metadata": {
                    "user_id": current_user.id,
                    "credits": credits_to_add,
                    "package_id": package_id
                }
            }

            response = requests.post(url, json=payload, headers=headers, timeout=15)
            result = response.json()

            if result.get('status') and result['data'].get('authorization_url'):
                # Redirect user to Paystack checkout
                return redirect(result['data']['authorization_url'])
            else:
                flash('Could not start Paystack payment.', 'danger')
                return redirect(url_for('profile.buy_credits'))

        except Exception as e:
            flash(f'Paystack error: {str(e)}', 'danger')
            return redirect(url_for('profile.buy_credits'))

    # GET request - show the page
    return render_template(
        'profile/buy_credits.html',
        packages=packages,
        max_note=max_note,
        current_balance=current_user.credit_balance or 0,
        is_business=is_business,
        account_type_label='Business' if is_business else 'Personal'
    )


@profile_bp.route('/payment-success')
@login_required
def payment_success():
    """Paystack redirects here after successful payment (we verify via webhook for security)"""
    flash('Payment successful! Your credits will be added shortly.', 'success')
    return redirect(url_for('profile.buy_credits'))


@profile_bp.route('/payment-cancel')
@login_required
def payment_cancel():
    flash('Payment was cancelled.', 'info')
    return redirect(url_for('profile.buy_credits'))


@profile_bp.route('/paystack-webhook', methods=['POST'])
def paystack_webhook():
    """Verify Paystack payment and credit the user"""
    try:
        payload = request.get_json()
        event = payload.get('event')

        if event == 'charge.success':
            data = payload.get('data', {})
            reference = data.get('reference')
            metadata = data.get('metadata', {})

            if reference:
                txn = CreditTransaction.query.filter_by(reference=reference).first()
                if txn and txn.status != 'success':
                    credits = int(metadata.get('credits', 0))
                    user = User.query.get(txn.user_id)
                    if user and credits > 0:
                        user.credit_balance = (user.credit_balance or 0) + credits
                        txn.status = 'success'
                        txn.transaction_type = 'purchase'
                        db.session.commit()

        return '', 200
    except Exception:
        return '', 200


@profile_bp.route('/', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        form = ProfileForm()
        if form.validate_on_submit():
            current_user.email = form.email.data
            current_user.phone = form.phone.data
            db.session.commit()
            flash('✅ Profile updated successfully!', 'success')
            return redirect(url_for('profile.profile'))
        # invalid POST: form has submitted data + errors, fall to render
    else:
        form = ProfileForm(obj=current_user)

    listings = Listing.query.filter_by(user_id=current_user.id, is_active=True)\
        .order_by(Listing.created_at.desc()).all()

    is_business = current_user.account_type == 'business' or current_user.is_business
    account_type_label = 'Business' if is_business else 'Personal'
    credit_balance = current_user.credit_balance or 0

    return render_template(
        'profile/profile.html',
        listings=listings,
        form=form,
        credit_balance=credit_balance,
        is_business=is_business,
        account_type_label=account_type_label
    )
