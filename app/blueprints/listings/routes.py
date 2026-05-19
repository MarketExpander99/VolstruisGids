from flask import render_template, redirect, url_for, flash
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
            is_business_ad=getattr(current_user, 'is_business', False),
            area=form.area.data
        )
        db.session.add(listing)
        db.session.commit()
        flash('Ad posted successfully!', 'success')
        return redirect(url_for('main.index'))
    
    return render_template('listings/create.html', form=form)

@listings_bp.route('/<int:listing_id>')
def detail(listing_id):
    listing = Listing.query.get_or_404(listing_id)
    return render_template('listings/detail.html', listing=listing)