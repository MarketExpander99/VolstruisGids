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
    """Redirect to the current Yoco-powered Buy Credits page.
    (Old Paystack implementation removed.)
    """
    flash('Credit purchases now use Yoco. Redirecting...', 'info')
    return redirect(url_for('payments.buy_credits'))


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

            # === One-way Personal -> Business Account Upgrade (ACCOUNT-BUSINESS-2026-06-20) ===
            # Non-downgradable. Triggered by filling business_name while personal.
            upgraded_now = False
            if not current_user.is_business_account:
                bn = (form.business_name.data or '').strip()
                if bn:
                    # Enforce required business fields for upgrade (per spec)
                    cp = (form.business_contact_person.data or '').strip()
                    bp = (form.business_phone.data or '').strip()
                    if not cp or not bp:
                        flash('To upgrade, please provide Business Name, Contact Person and Business Phone.', 'warning')
                    else:
                        current_user.is_business = True
                        current_user.account_type = 'business'
                        current_user.business_name = bn
                        current_user.business_type = (form.business_type.data or '').strip() or None
                        current_user.business_contact_person = cp
                        current_user.business_phone = bp
                        current_user.upgraded_at = datetime.utcnow()
                        # business_verified stays False (future manual/admin verify)
                        upgraded_now = True
                        flash('🎉 Account upgraded to Business! You now have the business badge and can post as a company.', 'success')

            db.session.commit()
            if not upgraded_now:
                flash('✅ Profile updated successfully!', 'success')
            return redirect(url_for('profile.profile'))

    else:
        form = ProfileForm(obj=current_user)

    # Note: Credits are only granted on confirmed success from payment_success or webhook,
    # not automatically on profile load (prevents add on cancel/abandon).

    # Show ALL user's listings (including expired/old) — owners must see them per spec.
    # Expired ones are visually marked in the template.
    listings = Listing.query.filter_by(user_id=current_user.id)\
        .order_by(Listing.created_at.desc()).all()

    is_business = current_user.is_business_account
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