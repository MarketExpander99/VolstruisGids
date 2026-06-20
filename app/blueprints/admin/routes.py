"""
Admin Panel routes (v1 MVP)
Protected exclusively via @admin_required (env-based usernames).
No model changes. Uses file audit log + existing CreditTransaction.
"""

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_
from decimal import Decimal, InvalidOperation
from werkzeug.security import generate_password_hash

from app import db
from app.models.user import User
from app.models.listing import Listing
from app.models.message import Message
from app.models.credit_transaction import CreditTransaction
from app.blueprints.admin import admin_bp
from app.blueprints.admin.forms import (
    UserSearchForm, UsernameChangeForm, PasswordResetForm,
    CreditAdjustForm, ListingEditForm
)
from app.utils.admin import (
    admin_required, is_admin, log_admin_action, generate_temp_password
)


@admin_bp.route('/')
@admin_required
def dashboard():
    """Simple admin landing with quick stats and navigation."""
    user_count = User.query.count()
    listing_count = Listing.query.count()
    active_listing_count = Listing.query.filter_by(is_active=True).count()
    credit_tx_count = CreditTransaction.query.count()

    # Show last 8 lines of audit log (best effort)
    audit_lines = []
    try:
        log_path = 'instance/admin_audit.log'
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-8:]
            audit_lines = [l.strip() for l in lines if l.strip()]
    except Exception:
        audit_lines = ["(no audit log yet)"]

    return render_template(
        'admin/dashboard.html',
        user_count=user_count,
        listing_count=listing_count,
        active_listing_count=active_listing_count,
        credit_tx_count=credit_tx_count,
        audit_lines=audit_lines
    )


@admin_bp.route('/users', methods=['GET', 'POST'])
@admin_required
def users():
    """Search users + list top results. Entry point for user operations."""
    form = UserSearchForm()
    q = request.args.get('q', request.form.get('q', '')).strip()

    query = User.query
    if q:
        like = f'%{q}%'
        # email may be NULL; use or_ safely
        query = query.filter(
            or_(
                User.username.ilike(like),
                User.email.ilike(like) if q else False
            )
        )

    # Order newest first, cap results for safety
    found_users = query.order_by(User.created_at.desc()).limit(100).all()

    return render_template(
        'admin/users.html',
        form=form,
        users=found_users,
        q=q
    )


@admin_bp.route('/user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def user_edit(user_id):
    """Single user management page: change username, reset password, adjust credits."""
    user = User.query.get_or_404(user_id)

    username_form = UsernameChangeForm()
    pw_form = PasswordResetForm()
    credit_form = CreditAdjustForm()

    # Prefill current username for change form display
    if request.method == 'GET':
        username_form.new_username.data = user.username

    temp_password_display = None  # Only populated on successful reset

    if request.method == 'POST':
        # === 1. Username change ===
        if 'new_username' in request.form and username_form.validate_on_submit():
            new_un = username_form.new_username.data.strip().lstrip('@')
            if new_un == user.username:
                flash('Username is unchanged.', 'info')
            else:
                # Check uniqueness
                exists = User.query.filter(User.username == new_un, User.id != user.id).first()
                if exists:
                    flash('That username is already taken.', 'danger')
                else:
                    old = user.username
                    user.username = new_un
                    db.session.commit()
                    log_admin_action('change_username', 'user', user.id, f"from={old} to={new_un}")
                    flash(f'Username changed from "{old}" to "{new_un}".', 'success')
                    return redirect(url_for('admin.user_edit', user_id=user.id))

        # === 2. Password reset (generate + show once) ===
        elif request.form.get('action') == 'reset_password' or 'confirm' in request.form:
            temp = generate_temp_password(10)
            user.password_hash = generate_password_hash(temp)
            db.session.commit()
            log_admin_action('reset_password', 'user', user.id, 'temp_password_issued')
            temp_password_display = temp
            flash('Temporary password generated. Communicate it securely to the user immediately.', 'warning')
            # Re-render so we can show the password in the template (one-time)

        # === 3. Credit adjustment ===
        elif 'amount' in request.form and credit_form.validate_on_submit():
            try:
                amount = credit_form.amount.data
                if amount is None:
                    amount = Decimal('0')
                reason = (credit_form.reason.data or '').strip()
                before = Decimal(str(user.credits or 0))
                after = before + amount

                # Apply via property/setter for both columns
                user.credits = after

                tx = CreditTransaction(
                    user_id=user.id,
                    amount=amount,
                    transaction_type='admin_adjust',
                    reference=reason[:255] if reason else 'admin_manual'
                )
                db.session.add(tx)
                db.session.commit()

                log_admin_action('adjust_credits', 'user', user.id,
                                 f"delta={amount} before={before} after={after} reason={reason}")
                flash(f'Credits adjusted by {amount}. New balance: {after}', 'success')
                return redirect(url_for('admin.user_edit', user_id=user.id))
            except (InvalidOperation, Exception) as e:
                db.session.rollback()
                flash(f'Credit adjustment failed: {e}', 'danger')

    # Fresh credit balance for display
    current_credits = user.credits

    return render_template(
        'admin/user_edit.html',
        user=user,
        username_form=username_form,
        pw_form=pw_form,
        credit_form=credit_form,
        current_credits=current_credits,
        temp_password_display=temp_password_display
    )


@admin_bp.route('/listings', methods=['GET'])
@admin_required
def listings():
    """Basic listing management overview + search."""
    q = request.args.get('q', '').strip()
    query = Listing.query
    if q:
        like = f'%{q}%'
        query = query.filter(
            or_(
                Listing.title.ilike(like),
                Listing.description.ilike(like)
            )
        )
    listings = query.order_by(Listing.created_at.desc()).limit(80).all()
    return render_template('admin/listings.html', listings=listings, q=q)


@admin_bp.route('/listing/<int:listing_id>', methods=['GET', 'POST'])
@admin_required
def listing_edit(listing_id):
    """Edit title/description or delete a listing."""
    listing = Listing.query.get_or_404(listing_id)
    form = ListingEditForm()

    if request.method == 'GET':
        form.title.data = listing.title
        form.description.data = listing.description

    if request.method == 'POST':
        # Delete action (with safe FK handling for messages)
        if request.form.get('delete') == '1':
            try:
                # Detach any messages referencing this listing (FK is nullable)
                Message.query.filter_by(listing_id=listing.id).update({Message.listing_id: None})
                log_admin_action('delete_listing', 'listing', listing.id,
                                 f"title={listing.title[:60]} user_id={listing.user_id}")
                db.session.delete(listing)
                db.session.commit()
                flash('Listing permanently deleted.', 'success')
                return redirect(url_for('admin.listings'))
            except Exception as e:
                db.session.rollback()
                flash(f'Delete failed: {e}', 'danger')

        # Deactivate (soft)
        if request.form.get('deactivate') == '1':
            listing.is_active = False
            db.session.commit()
            log_admin_action('deactivate_listing', 'listing', listing.id, '')
            flash('Listing deactivated (hidden from public).', 'success')
            return redirect(url_for('admin.listing_edit', listing_id=listing.id))

        # Save edits
        if form.validate_on_submit():
            listing.title = form.title.data.strip()
            listing.description = form.description.data.strip()
            db.session.commit()
            log_admin_action('edit_listing', 'listing', listing.id, f"title={listing.title[:50]}")
            flash('Listing updated.', 'success')
            return redirect(url_for('admin.listing_edit', listing_id=listing.id))

    return render_template(
        'admin/listing_edit.html',
        listing=listing,
        form=form
    )
