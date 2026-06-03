from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app import db
from .forms import ProfileForm
from . import profile_bp
from datetime import datetime
from app.models.credit_transaction import CreditTransaction
from app.models.user import User
import urllib.request
import urllib.error
import json


@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)

    credit_balance = current_user.credit_balance or 0
    is_business = current_user.account_type == 'business' or current_user.is_business
    account_type_label = 'Business' if is_business else 'Personal'

    if form.validate_on_submit():
        current_user.phone = form.phone.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile.profile'))

    return render_template(
        'profile/profile.html',
        form=form,
        credit_balance=credit_balance,
        is_business=is_business,
        account_type_label=account_type_label
    )


@profile_bp.route('/buy-credits', methods=['GET', 'POST'])
@login_required
def buy_credits():
    """Buy Credits page with real Yoco integration + simulation fallback"""

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
        amount_cents = int(selected['price'] * 100)

        # === SIMULATION MODE (no key or test mode) ===
        if not current_app.config.get('YOCO_SECRET_KEY') or current_app.config.get('YOCO_TEST_MODE'):
            current_user.credit_balance = (current_user.credit_balance or 0) + credits_to_add
            txn = CreditTransaction(
                user_id=current_user.id,
                amount=credits_to_add,
                transaction_type='purchase',
                reference=f'sim_{package_id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
            )
            db.session.add(txn)
            try:
                db.session.commit()
                flash(f'✅ [SIM] Purchased {credits_to_add} credits for R{selected["price"]}! New balance: {current_user.credit_balance}', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('profile.buy_credits'))

        # === REAL YOCO CHECKOUT ===
        try:
            checkout_payload = {
                "amount": amount_cents,
                "currency": "ZAR",
                "successUrl": url_for('profile.payment_success', _external=True),
                "cancelUrl": url_for('profile.payment_cancel', _external=True),
                "notifyUrl": url_for('profile.yoco_webhook', _external=True),
                "metadata": {
                    "user_id": current_user.id,
                    "credits": credits_to_add,
                    "package_id": package_id
                }
            }

            req = urllib.request.Request(
                'https://api.yoco.com/v1/checkouts',
                data=json.dumps(checkout_payload).encode('utf-8'),
                headers={
                    'Authorization': f'Bearer {current_app.config["YOCO_SECRET_KEY"]}',
                    'Content-Type': 'application/json'
                },
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode())

            redirect_url = result.get('redirectUrl') or result.get('url')
            if redirect_url:
                return redirect(redirect_url)
            else:
                flash('Could not start Yoco payment.', 'danger')

        except urllib.error.HTTPError as e:
            flash(f'Yoco error: {e.read().decode()}', 'danger')
        except Exception as e:
            flash(f'Payment failed: {str(e)}', 'danger')

        return redirect(url_for('profile.buy_credits'))

    # GET
    return render_template(
        'profile/buy_credits.html',
        packages=packages,
        max_note=max_note,
        current_balance=current_user.credit_balance or 0,
        is_business=is_business,
        account_type_label='Business' if is_business else 'Personal'
    )