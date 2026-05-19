from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.listing import Listing
from .forms import ListingForm
from . import listings_bp

@listings_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    form = ListingForm()
    if form.validate_on_submit():
        listing = Listing(
            user_id=current_user.id,
            title=form.title.data,
            description=form.description.data,
            price=form.price.data,
            is_business_ad=current_user.is_business,
            area=form.area.data,
            category_id=1  # placeholder for now
        )
        db.session.add(listing)
        db.session.commit()
        flash('Ad posted successfully!', 'success')
        return redirect(url_for('main.index'))
    
    return render_template('listings/create.html', form=form)