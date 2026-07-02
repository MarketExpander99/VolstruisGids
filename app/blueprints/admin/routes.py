"""
Admin Panel routes (VGS-003)
Protected exclusively via @admin_required (env-based ADMIN_USERNAMES whitelist on normal logged-in users).
Core: users, listings (suspend/activate), credit adjust, Polish-with-Grok (before/after + auto reindex).
No model changes. File audit log + CreditTransaction for history.
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
from app.models.category import Category
from app.models.psa_banner import PSABanner
from app.blueprints.admin import admin_bp
from app.blueprints.admin.forms import (
    UserSearchForm, UsernameChangeForm, PasswordResetForm,
    CreditAdjustForm, ListingEditForm, PSABannerForm
)
from app.utils.admin import (
    admin_required, is_admin, log_admin_action, generate_temp_password
)
from app.services.google_indexing import notify_listing_change
from app.services.grok_polish import perform_grok_polish


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

    # Prefill current username for change form display (strip legacy leading @ for clean @-prefix UX)
    if request.method == 'GET':
        username_form.new_username.data = (user.username or '').lstrip('@')

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

        # === 4. Business verification toggle (new Directory feature) ===
        elif request.form.get('action') == 'toggle_business_verify':
            user.business_verified = not bool(user.business_verified)
            db.session.commit()
            status = 'VERIFIED' if user.business_verified else 'un-verified'
            log_admin_action('toggle_business_verify', 'user', user.id, f"set={status}")
            flash(f'Business account marked as {status}.', 'success')
            return redirect(url_for('admin.user_edit', user_id=user.id))

        # === 5. Toggle full Business Account status (is_business + account_type) ===
        elif request.form.get('action') == 'toggle_business_account':
            if user.is_business_account:
                user.is_business = False
                user.account_type = 'personal'
                user.business_verified = False  # demoted accounts should not stay verified
                # Keep business_name / other fields so admin re-promote or user re-upgrade is easy
                action_desc = 'demoted to personal'
            else:
                user.is_business = True
                user.account_type = 'business'
                action_desc = 'promoted to business'
            db.session.commit()
            log_admin_action('toggle_business_account', 'user', user.id, action_desc)
            flash(f'Account {action_desc}. It will now appear (or disappear) in the Business Directory.', 'success')
            return redirect(url_for('admin.user_edit', user_id=user.id))

    # Fresh credit balance for display
    current_credits = user.credits

    # Recent listings for the user details view (spec: View user details (listings, credits))
    user_listings = (
        Listing.query.filter_by(user_id=user.id)
        .order_by(Listing.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        'admin/user_edit.html',
        user=user,
        username_form=username_form,
        pw_form=pw_form,
        credit_form=credit_form,
        current_credits=current_credits,
        temp_password_display=temp_password_display,
        user_listings=user_listings
    )


@admin_bp.route('/listings', methods=['GET'])
@admin_required
def listings():
    """Listing management: search + status filter (active/suspended/all)."""
    q = request.args.get('q', '').strip()
    status = request.args.get('status', 'active').strip().lower()  # default to active per common ops

    query = Listing.query
    if q:
        like = f'%{q}%'
        query = query.filter(
            or_(
                Listing.title.ilike(like),
                Listing.description.ilike(like)
            )
        )

    if status == 'active':
        query = query.filter(Listing.is_active == True)
    elif status == 'suspended':
        query = query.filter(Listing.is_active == False)
    # 'all' or anything else: no filter

    listings = query.order_by(Listing.created_at.desc()).limit(80).all()
    return render_template('admin/listings.html', listings=listings, q=q, status=status)


@admin_bp.route('/listing/<int:listing_id>/toggle', methods=['POST'])
@admin_required
def toggle_listing(listing_id):
    """Quick activate/suspend from listings table."""
    listing = Listing.query.get_or_404(listing_id)
    action = request.form.get('action', '')
    was_active = bool(listing.is_active)

    if action == 'suspend':
        listing.is_active = False
        db.session.commit()
        log_admin_action('suspend_listing', 'listing', listing.id, f"title={listing.title[:50]}")
        try:
            listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
            notify_listing_change(listing_url, "URL_DELETED")
        except Exception:
            pass
        flash('Listing suspended (hidden from public).', 'warning')
    elif action == 'activate':
        listing.is_active = True
        db.session.commit()
        log_admin_action('activate_listing', 'listing', listing.id, f"title={listing.title[:50]}")
        try:
            listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
            notify_listing_change(listing_url, "URL_UPDATED")
        except Exception:
            pass
        flash('Listing activated.', 'success')
    else:
        flash('Unknown toggle action.', 'danger')

    # Preserve current filter/search if possible
    return redirect(request.referrer or url_for('admin.listings'))


@admin_bp.route('/listing/<int:listing_id>/polish', methods=['GET', 'POST'])
@admin_required
def polish_listing(listing_id):
    """
    Polish with Grok flow for admin (per VGS-003 spec).
    - GET: Call Grok, render before/after preview + confirmation form.
    - POST (confirm): Apply polished title+desc, save, log, trigger re-index.
    Reuses existing Grok polish logic. Admin action is free / bypasses user rate limits.
    """
    listing = Listing.query.get_or_404(listing_id)

    if request.method == 'POST' and request.form.get('apply_polish') == '1':
        # Apply from the confirmed values (submitted from preview to avoid surprise re-calls)
        new_title = (request.form.get('polished_title') or listing.title).strip()
        new_desc = (request.form.get('polished_description') or listing.description).strip()

        if not new_title or not new_desc:
            flash('Cannot apply empty polished content.', 'danger')
            return redirect(url_for('admin.polish_listing', listing_id=listing.id))

        old_title = listing.title
        old_desc = listing.description

        listing.title = new_title
        listing.description = new_desc
        db.session.commit()

        log_admin_action(
            'polish_with_grok',
            'listing',
            listing.id,
            f"title_before={old_title[:60]} title_after={new_title[:60]}"
        )

        # Same re-index flow as normal edit
        try:
            listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
            notify_listing_change(listing_url, "URL_UPDATED")
        except Exception as _e:
            print(f"[GOOGLE INDEXING] Skipped (non-fatal): {_e}")

        flash('Listing polished with Grok, saved, and re-index triggered.', 'success')
        return redirect(url_for('admin.listing_edit', listing_id=listing.id))

    # GET: fetch fresh polish preview
    try:
        # Gather light context
        cat_name = ''
        if listing.category_id:
            cat = Category.query.get(listing.category_id)
            if cat:
                cat_name = cat.name

        town = listing.get_town_display() if hasattr(listing, 'get_town_display') else (listing.area or listing.location or '')

        result = perform_grok_polish(
            title=listing.title or '',
            description=listing.description or '',
            post_type=listing.post_type or 'sale',
            category_name=cat_name,
            town=town,
            price=str(listing.price) if listing.price is not None else '',
            price_type=listing.price_type or 'fixed'
        )

        polished_title = result.get('polished_title') or listing.title
        polished_description = result.get('polished_description') or listing.description

    except Exception as e:
        flash(f'Grok polish failed: {e}', 'danger')
        return redirect(url_for('admin.listing_edit', listing_id=listing.id))

    return render_template(
        'admin/polish_preview.html',
        listing=listing,
        before_title=listing.title,
        before_description=listing.description,
        polished_title=polished_title,
        polished_description=polished_description
    )


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
                listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
                log_admin_action('delete_listing', 'listing', listing.id,
                                 f"title={listing.title[:60]} user_id={listing.user_id}")
                db.session.delete(listing)
                db.session.commit()

                # Google Indexing: remove from search
                try:
                    notify_listing_change(listing_url, "URL_DELETED")
                except Exception as _e:
                    print(f"[GOOGLE INDEXING] Skipped (non-fatal): {_e}")

                flash('Listing permanently deleted.', 'success')
                return redirect(url_for('admin.listings'))
            except Exception as e:
                db.session.rollback()
                flash(f'Delete failed: {e}', 'danger')

        # Suspend (soft hide, aka deactivate)
        if request.form.get('suspend') == '1' or request.form.get('deactivate') == '1':
            listing.is_active = False
            db.session.commit()
            log_admin_action('suspend_listing', 'listing', listing.id, '')

            # Google Indexing: remove from search (soft delete)
            try:
                listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
                notify_listing_change(listing_url, "URL_DELETED")
            except Exception as _e:
                print(f"[GOOGLE INDEXING] Skipped (non-fatal): {_e}")

            flash('Listing suspended (hidden from public).', 'warning')
            return redirect(url_for('admin.listing_edit', listing_id=listing.id))

        # Activate
        if request.form.get('activate') == '1':
            listing.is_active = True
            db.session.commit()
            log_admin_action('activate_listing', 'listing', listing.id, '')

            try:
                listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
                notify_listing_change(listing_url, "URL_UPDATED")
            except Exception as _e:
                print(f"[GOOGLE INDEXING] Skipped (non-fatal): {_e}")

            flash('Listing activated and visible to public.', 'success')
            return redirect(url_for('admin.listing_edit', listing_id=listing.id))

        # Save edits
        if form.validate_on_submit():
            listing.title = form.title.data.strip()
            listing.description = form.description.data.strip()
            db.session.commit()
            log_admin_action('edit_listing', 'listing', listing.id, f"title={listing.title[:50]}")

            # Google Indexing: updated content
            try:
                listing_url = url_for('listings.detail', listing_id=listing.id, _external=True)
                notify_listing_change(listing_url, "URL_UPDATED")
            except Exception as _e:
                print(f"[GOOGLE INDEXING] Skipped (non-fatal): {_e}")

            flash('Listing updated.', 'success')
            return redirect(url_for('admin.listing_edit', listing_id=listing.id))

    return render_template(
        'admin/listing_edit.html',
        listing=listing,
        form=form
    )


# ============================================================
# VGS-004: Admin PSA / News Banner Management
# ============================================================

@admin_bp.route('/psa-banners', methods=['GET', 'POST'])
@admin_required
def psa_banners():
    """List all PSA banners + quick create form."""
    form = PSABannerForm()

    if request.method == 'POST' and form.validate_on_submit():
        banner = PSABanner(
            title=form.title.data.strip(),
            content=(form.content.data or '').strip() or None,
            banner_type=form.banner_type.data,
            color=form.color.data,
            active=bool(form.active.data),
            priority=int(form.priority.data or 0),
            link=(form.link.data or '').strip() or None,
            expiry=form.expiry.data
        )
        db.session.add(banner)
        db.session.commit()
        log_admin_action('create_psa_banner', 'psa_banner', banner.id, f"title={banner.title[:50]} type={banner.banner_type}")
        flash('PSA Banner created.', 'success')
        return redirect(url_for('admin.psa_banners'))

    # Show all (admin sees inactive/expired too), newest first
    banners = PSABanner.query.order_by(PSABanner.priority.desc(), PSABanner.created_at.desc()).all()
    return render_template('admin/psa_banners.html', form=form, banners=banners)


@admin_bp.route('/psa-banner/<int:banner_id>', methods=['GET', 'POST'])
@admin_required
def psa_banner_edit(banner_id):
    """Edit an existing banner. Also used for preview."""
    banner = PSABanner.query.get_or_404(banner_id)
    form = PSABannerForm(obj=banner)

    if request.method == 'GET':
        # Prefill
        form.active.data = banner.active

    if request.method == 'POST':
        if request.form.get('delete') == '1':
            log_admin_action('delete_psa_banner', 'psa_banner', banner.id, f"title={banner.title[:50]}")
            db.session.delete(banner)
            db.session.commit()
            flash('Banner permanently deleted.', 'success')
            return redirect(url_for('admin.psa_banners'))

        if form.validate_on_submit():
            banner.title = form.title.data.strip()
            banner.content = (form.content.data or '').strip() or None
            banner.banner_type = form.banner_type.data
            banner.color = form.color.data
            banner.active = bool(form.active.data)
            banner.priority = int(form.priority.data or 0)
            banner.link = (form.link.data or '').strip() or None
            banner.expiry = form.expiry.data
            db.session.commit()
            log_admin_action('update_psa_banner', 'psa_banner', banner.id, f"title={banner.title[:50]} active={banner.active}")
            flash('Banner updated.', 'success')
            return redirect(url_for('admin.psa_banner_edit', banner_id=banner.id))

        # Quick toggle from edit page
        if request.form.get('toggle_active') == '1':
            banner.active = not banner.active
            db.session.commit()
            log_admin_action('toggle_psa_banner', 'psa_banner', banner.id, f"active={banner.active}")
            flash(f'Banner {"activated" if banner.active else "deactivated"}.', 'success')
            return redirect(url_for('admin.psa_banner_edit', banner_id=banner.id))

    # Live preview data for template
    return render_template(
        'admin/psa_banner_edit.html',
        banner=banner,
        form=form
    )


@admin_bp.route('/psa-banner/<int:banner_id>/toggle', methods=['POST'])
@admin_required
def toggle_psa_banner(banner_id):
    """Quick active toggle from list."""
    banner = PSABanner.query.get_or_404(banner_id)
    banner.active = not banner.active
    db.session.commit()
    log_admin_action('toggle_psa_banner', 'psa_banner', banner.id, f"active={banner.active}")
    flash(f'Banner {"activated" if banner.active else "deactivated"}.', 'success')
    return redirect(request.referrer or url_for('admin.psa_banners'))
