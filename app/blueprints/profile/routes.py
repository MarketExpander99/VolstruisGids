import os
from datetime import datetime
from decimal import Decimal
from flask import render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.models.listing import Listing
from .forms import ProfileForm
import requests
from werkzeug.utils import secure_filename
from PIL import Image

from app.blueprints.profile import profile_bp

UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def resize_image_to_square(image_path, size=400):
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            if width > height:
                left = (width - height) // 2
                top = 0
                right = left + height
                bottom = height
            else:
                left = 0
                top = (height - width) // 2
                right = width
                bottom = top + width
            img = img.crop((left, top, right, bottom))
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            img.save(image_path)
        return True
    except Exception:
        return False


# ============================================================
# BUY CREDITS + PAYSTACK
# ============================================================

@profile_bp.route('/buy-credits', methods=['GET', 'POST'])
@login_required
def buy_credits():
    """Buy Credits page - powered by Paystack"""

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

    if request.method == 'POST':
        package_id = request.form.get('package_id')
        selected = next((p for p in packages if p['id'] == package_id), None)

        if not selected:
            flash('Invalid package selected.', 'danger')
            return redirect(url_for('profile.buy_credits'))

        credits_to_add = selected['credits']
        amount = selected['price']

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

        # Paystack Integration
        try:
            secret_key = current_app.config.get('PAYSTACK_SECRET_KEY')
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

            if result.get('status') and result['data'].get('authorization_url'):
                return redirect(result['data']['authorization_url'])
            else:
                flash(f'Paystack error: {result}', 'danger')
                return redirect(url_for('profile.buy_credits'))

        except Exception as e:
            flash(f'Paystack exception: {str(e)}', 'danger')
            return redirect(url_for('profile.buy_credits'))

    # GET request
    return render_template(
        'profile/buy_credits.html',
        packages=packages,
        max_note=max_note,
        current_balance=current_user.credit_balance or Decimal('0'),
        is_business=is_business,
        account_type_label='Business' if is_business else 'Personal'
    )


@profile_bp.route('/payment-success')
@login_required
def payment_success():
    flash('Payment successful! Your credits will be added shortly.', 'success')
    return redirect(url_for('profile.buy_credits'))


@profile_bp.route('/payment-cancel')
@login_required
def payment_cancel():
    flash('Payment was cancelled.', 'info')
    return redirect(url_for('profile.buy_credits'))


@profile_bp.route('/paystack-webhook', methods=['POST'])
def paystack_webhook():
    try:
        payload = request.get_json()
        if payload.get('event') == 'charge.success':
            data = payload.get('data', {})
            reference = data.get('reference')
            metadata = data.get('metadata', {})

            if reference:
                txn = CreditTransaction.query.filter_by(reference=reference).first()
                if txn and txn.status != 'success':
                    credits = int(metadata.get('credits', 0))
                    user = User.query.get(txn.user_id)
                    if user and credits > 0:
                        user.credit_balance = (user.credit_balance or Decimal('0')) + Decimal(str(credits))
                        txn.status = 'success'
                        db.session.commit()
        return '', 200
    except Exception:
        return '', 200


# ============================================================
# PROFILE PAGE + LOGO UPLOAD
# ============================================================

@profile_bp.route('/', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        form = ProfileForm()
        if form.validate_on_submit():
            current_user.email = form.email.data
            current_user.phone = form.phone.data

            # === Business Logo Upload ===
            if form.photo.data:
                file = form.photo.data
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                    file.save(filepath)
                    resize_image_to_square(filepath)
                    current_user.profile_pic = f'/static/uploads/{filename}'

            db.session.commit()
            flash('✅ Profile updated successfully!', 'success')
            return redirect(url_for('profile.profile'))

    else:
        form = ProfileForm(obj=current_user)

    # Show ALL user's listings (including expired/old) — owners must see them per spec.
    # Expired ones are visually marked in the template.
    listings = Listing.query.filter_by(user_id=current_user.id)\
        .order_by(Listing.created_at.desc()).all()

    is_business = current_user.account_type == 'business' or current_user.is_business
    account_type_label = 'Business' if is_business else 'Personal'
    credit_balance = current_user.credit_balance or Decimal('0')

    return render_template(
        'profile/profile.html',
        listings=listings,
        form=form,
        credit_balance=credit_balance,
        is_business=is_business,
        account_type_label=account_type_label
    )