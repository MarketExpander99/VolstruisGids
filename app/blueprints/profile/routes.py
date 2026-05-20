from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from .forms import ProfileForm
from . import profile_bp

@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)  # Pre-fill current data
    
    if form.validate_on_submit():
        current_user.phone = form.phone.data
        current_user.email = form.email.data
        # Add more fields later (name, bio, etc.)
        
        db.session.commit()
        flash('✅ Profile updated successfully!', 'success')
        return redirect(url_for('profile.profile'))
    
    return render_template('profile/profile.html', form=form)