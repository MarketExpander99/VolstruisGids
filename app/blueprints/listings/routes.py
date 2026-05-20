from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from .forms import ListingForm
from . import listings_bp
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@listings_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = ListingForm()
    if form.validate_on_submit():
        photo_url = None

        # Photo upload handling
        if form.photo.data and allowed_file(form.photo.data.filename):
            filename = secure_filename(form.photo.data.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            form.photo.data.save(filepath)
            photo_url = f'/static/uploads/{filename}'

        # Create listing with ONLY valid fields
        listing = Listing(
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            location=form.location.data,
            area=form.area.data or "Klein Karoo",
            contact_phone=form.contact_phone.data,
            contact_email=form.contact_email.data,
            category_id=form.category.data,
            user_id=current_user.id,
            photo_url=photo_url
        )
        
        db.session.add(listing)
        db.session.commit()
        
        flash('Listing created successfully! ✅', 'success')
        return redirect(url_for('main.index'))
    
    return render_template('listings/create.html', form=form)