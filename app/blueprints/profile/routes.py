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

            db.session.commit()
            flash('✅ Profile updated successfully!', 'success')
            return redirect(url_for('profile.profile'))

    else:
        form = ProfileForm(obj=current_user)

    # Auto-claim any recent pending Yoco credit purchases so balance is always up-to-date
    # (handles redirect cases where checkout id may not be in the success URL).
    try:
        from datetime import datetime, timedelta
        from app.models.credit_transaction import CreditTransaction
        from app.blueprints.payments.routes import _fulfill_credit_purchase
        cutoff = datetime.utcnow() - timedelta(minutes=60)
        for ptxn in CreditTransaction.query.filter(
            CreditTransaction.user_id == current_user.id,
            CreditTransaction.transaction_type == 'purchase',
            CreditTransaction.created_at >= cutoff
        ).all():
            if getattr(ptxn, 'status', None) != 'success' and (ptxn.amount or 0) > 0:
                _fulfill_credit_purchase(ptxn.reference)
    except Exception:
        pass  # non-fatal

    # Refresh so the just-claimed credits are visible on this render
    if current_user.is_authenticated:
        try:
            db.session.refresh(current_user)
        except Exception:
            db.session.expire(current_user)

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