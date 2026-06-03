from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from .forms import ProfileForm
from . import profile_bp
from datetime import datetime
from app.models.credit_transaction import CreditTransaction


@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)  # Pre-fill current data

    # Prepare credit info for the template
    credit_balance = current_user.credit_balance or 0
    is_business = current_user.account_type == 'business' or current_user.is_business
    account_type_label = 'Business' if is_business else 'Personal'

    if form.validate_on_submit():
        current_user.phone = form.phone.data
        current_user.email = form.email.data
        # Add more fields later (name, bio, etc.)

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
    """Buy Credits page - v1.0 (simulated purchase for testing, real Yoco coming next)"""

    # Personal packages (max 10 credits per purchase per spec)
    personal_packages = [
        {"id": "small", "name": "Small", "credits": 5, "price": 55, "note": "Easy entry"},
        {"id": "standard", "name": "Standard", "credits": 10, "price": 99, "note": "Best value for personal"},
    ]

    # Business packages (volume discounts)
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

        if selected:
            credits_to_add = selected['credits']
            current_user.credit_balance = (current_user.credit_balance or 0) + credits_to_add

            txn = CreditTransaction(
                user_id=current_user.id,
                amount=credits_to_add,
                transaction_type='purchase',
                reference=f'sim_purchase_{package_id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
            )
            db.session.add(txn)

            try:
                db.session.commit()
                flash(
                    f'✅ Successfully purchased {credits_to_add} credits for R{selected["price"]}! '
                    f'New balance: {current_user.credit_balance}',
                    'success'
                )
            except Exception as e:
                db.session.rollback()
                flash(f'Error processing purchase: {str(e)}', 'danger')
        else:
            flash('Invalid package selected. Please try again.', 'danger')

        return redirect(url_for('profile.buy_credits'))

    # GET render
    return render_template(
        'profile/buy_credits.html',
        packages=packages,
        max_note=max_note,
        current_balance=current_user.credit_balance or 0,
        is_business=is_business,
        account_type_label='Business' if is_business else 'Personal'
    )