from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
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

        # === Warm Fire Starter - Separate caps for Personal vs Business ===
        base_credits = 50
        bonus = 0
        is_early = False

        if form.is_business.data:
            # Business accounts - first 50 get stronger early bonus
            business_count = User.query.filter_by(is_business=True).count()
            if business_count < 60:
                bonus = 150          # Early business = 200 total credits
                is_early = True
        else:
            # Personal accounts - first 150 get bonus
            personal_count = User.query.filter_by(is_business=False).count()
            if personal_count < 160:
                bonus = 100          # Early personal = 150 total credits
                is_early = True

        user.credit_balance = base_credits + bonus

        db.session.add(user)
        db.session.flush()  # Get user.id

        # Record the grant in credit_transactions for history/audit
        if is_early:
            tx_type = 'early_business_grant' if form.is_business.data else 'early_personal_grant'
            tx = CreditTransaction(
                user_id=user.id,
                amount=base_credits + bonus,
                transaction_type=tx_type,
                reference='initial_free_credits'
            )
            db.session.add(tx)

        db.session.commit()

        if is_early:
            total = base_credits + bonus
            if form.is_business.data:
                flash(f'Registration successful! Welcome, early business supporter! You have received {total} free credits (50 base + 150 early-business bonus).', 'success')
            else:
                flash(f'Registration successful! Welcome, early supporter! You have received {total} free credits (50 base + 100 early-adopter bonus).', 'success')
        else:
            flash('Registration successful! You have received 50 free starting credits.', 'success')

        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))