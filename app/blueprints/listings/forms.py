from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, FloatField, SelectField, 
    FileField, MultipleFileField, SubmitField, RadioField, 
    BooleanField, IntegerField, SelectMultipleField
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

# Import canonical towns for multi-select (VGS-002). Do NOT duplicate lists.
from app.models.listing import Listing


class ListingForm(FlaskForm):
    post_type = RadioField('Post Type', validators=[DataRequired()], choices=[
        ('sale', '🛒 Items for Sale'),
        ('wanted', '🔍 Looking for'),
        ('rental', '🔄 For Rent / Hire'),
        ('services', '🛠 Services Offered'),
        ('announcement', '📢 General Announcement'),
        ('event', '🎉 Event')
    ], default='sale')

    price_type = RadioField('Price Type', validators=[DataRequired()], choices=[
        ('fixed', 'Fixed Price'),
        ('range', 'Price Range')
    ], default='fixed')

    price = FloatField('Price (ZAR)', validators=[Optional(), NumberRange(min=0)])
    min_price = FloatField('Min Price (ZAR)', validators=[Optional(), NumberRange(min=0)])
    max_price = FloatField('Max Price (ZAR)', validators=[Optional(), NumberRange(min=0)])

    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=2000)])

    category = SelectField('Category', coerce=int, validators=[DataRequired()])

    # VGS-002: Multi-town select. Uses exact list from prior single-town + homepage.
    # Klein Karoo option = full region coverage (special handling in filters/display).
    _town_choices = [(t, t) for t in Listing.TOWNS]
    _town_choices.append((Listing.KLEIN_KAROO, 'Klein Karoo (entire region)'))
    town = SelectMultipleField(
        'Towns / Areas (select all that apply)',
        choices=_town_choices,
        validators=[DataRequired(message="Please select at least one town or region.")]
    )

    # Multi-select contact methods
    contact_methods = SelectMultipleField(
        'How would you like to be contacted? (select all that apply)',
        choices=[
            ('dm', '💬 DM (Private Message via the platform)'),
            ('email', '📧 Email'),
            ('phone', '📞 Phone (WhatsApp)')
        ],
        validators=[DataRequired(message="Please select at least one contact method.")],
        default=['dm', 'email', 'phone']
    )

    allow_comments = BooleanField('Allow comments on this listing', default=True)

    contact_phone = StringField('Contact Phone')
    contact_email = StringField('Contact Email')

    # Changed to MultipleFileField so multiple photos work properly
    photo = MultipleFileField('Photos (optional)')

    # Rental fields
    rental_duration = IntegerField('Rental Duration', validators=[Optional(), NumberRange(min=1)])
    rental_duration_unit = SelectField('Duration Unit', choices=[
        ('day', 'Day(s)'),
        ('week', 'Week(s)'),
        ('month', 'Month(s)')
    ], default='day', validators=[Optional()])


class CommentForm(FlaskForm):
    """Simple comment form for detail page only (per engagement spec)."""
    text = TextAreaField('Comment', validators=[DataRequired(), Length(min=1, max=2000)])
    submit = SubmitField('Post Comment')
