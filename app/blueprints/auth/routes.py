from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.user import User
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
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))