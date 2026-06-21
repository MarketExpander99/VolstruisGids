from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal
from app import db
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.blueprints.auth import auth_bp
from app.blueprints.auth.forms import LoginForm, RegistrationForm

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        login_username = form.username.data.strip().lstrip('@')
        user = User.query.filter_by(username=login_username).first()
        if not user:
            # try with @ for legacy users who registered with @ in name
            user = User.query.filter_by(username='@' + login_username).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember_me.data)
            user.ensure_daily_free_credits()
            # Sync share-to-earn counter from tx log so denorm fields are accurate for the new day
            try:
                user.sync_share_reward_counter()
            except Exception:
                pass
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        flash('Invalid username or password')
    return render_template('auth/login.html', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        # Normalize username: strip whitespace and leading @ (to avoid @@User in displays)
        clean_username = form.username.data.strip().lstrip('@')
        user = User(
            username=clean_username,
            phone=form.phone.data,
            email=form.email.data if form.email.data else None,
            password_hash=generate_password_hash(form.password.data),
            is_business=form.is_business.data,
            business_name=form.business_name.data.strip() if form.is_business.data and form.business_name.data else None
        )

        # Set account_type consistently with is_business flag
        user.account_type = 'business' if form.is_business.data else 'personal'

        # Base starter credits (generous for usability)
        base_credits = Decimal('50')
        user.credit_balance = base_credits

        # === Launch Bonus (v1.2 Final Spec): first 100 personal + first 20 business get +5 ===
        from sqlalchemy import func
        total_personal = User.query.filter(User.is_business == False).count()
        total_business = User.query.filter(User.is_business == True).count()

        launch_bonus = Decimal('0')
        is_launch_early = False
        if not form.is_business.data:
            if total_personal <= 100:
                launch_bonus = Decimal('5')
                is_launch_early = True
        else:
            if total_business <= 20:
                launch_bonus = Decimal('5')
                is_launch_early = True

        if launch_bonus > 0:
            user.credit_balance = (user.credit_balance or Decimal('0')) + launch_bonus

        db.session.add(user)
        db.session.flush()  # Get user.id

        # Record the grant in credit_transactions for history/audit
        if is_launch_early:
            tx = CreditTransaction(
                user_id=user.id,
                amount=base_credits + launch_bonus,
                transaction_type='launch_bonus' if not form.is_business.data else 'launch_bonus_business',
                reference='initial_free_credits'
            )
            db.session.add(tx)
        else:
            # Always record base starter for audit
            tx = CreditTransaction(
                user_id=user.id,
                amount=base_credits,
                transaction_type='starter_credits',
                reference='initial_free_credits'
            )
            db.session.add(tx)

        db.session.commit()

        total = user.credit_balance or base_credits
        if is_launch_early:
            if form.is_business.data:
                flash(f'Registration successful! Welcome, early business supporter! You have received {total} credits (incl. +5 launch bonus).', 'success')
            else:
                flash(f'Registration successful! Welcome, early supporter! You have received {total} credits (incl. +5 launch bonus).', 'success')
        else:
            flash(f'Registration successful! You have received {base_credits} starting credits.', 'success')

        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))