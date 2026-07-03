from flask_wtf import FlaskForm
from wtforms import (
    StringField, IntegerField, DecimalField, TextAreaField, SubmitField, HiddenField,
    SelectField, BooleanField, DateTimeField, SelectMultipleField, MultipleFileField
)
from wtforms.validators import DataRequired, Length, Optional, NumberRange, Regexp
from wtforms.widgets import DateTimeInput  # for expiry input

# Import Listing for static choices (safe at import time per app bootstrap order)
from app.models.listing import Listing

# Canonical choices reused for admin full-edit form (no duplication of source of truth)
TOWN_CHOICES = [(t, t) for t in Listing.TOWNS] + [(Listing.KLEIN_KAROO, 'Klein Karoo (entire region)')]
CONTACT_METHOD_CHOICES = [
    ('dm', '💬 DM (in-app private message)'),
    ('email', '📧 Email'),
    ('phone', '📞 Phone / WhatsApp'),
]
POST_TYPE_CHOICES = [
    ('sale', '🛒 Items for Sale'),
    ('wanted', '🔍 Looking for (Wanted)'),
    ('rental', '🔄 For Rent / Hire'),
    ('services', '🛠 Services Offered'),
    ('announcement', '📢 General Announcement'),
    ('event', '🎉 Event'),
]


class UserSearchForm(FlaskForm):
    q = StringField('Search username or email', validators=[Optional(), Length(max=120)])
    submit = SubmitField('Search')


class UsernameChangeForm(FlaskForm):
    new_username = StringField('New Username', validators=[
        DataRequired(),
        Length(min=3, max=30),
        Regexp(r'^@?[a-zA-Z0-9_-]+$', message="Username can only contain letters, numbers, underscores and hyphens (leading @ is allowed but will be ignored).")
    ])
    submit = SubmitField('Change Username')

    def validate_new_username(self, field):
        if field.data:
            field.data = field.data.strip().lstrip('@')


class PasswordResetForm(FlaskForm):
    # No input needed — we generate secure temp password server-side
    confirm = HiddenField('confirm', default='yes')
    submit = SubmitField('Generate & Set Temporary Password')


class CreditAdjustForm(FlaskForm):
    amount = DecimalField('Amount (positive = add, negative = subtract)', validators=[DataRequired(), NumberRange(min=-10000, max=10000)], places=2)
    reason = StringField('Reason / Reference', validators=[DataRequired(), Length(min=3, max=200)])
    submit = SubmitField('Apply Credit Adjustment')


class ListingEditForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=2000)])
    submit = SubmitField('Save Changes')


# === VGS-004: PSA / News Banners ===
BANNER_TYPE_CHOICES = [
    ('alert', 'Alert (urgent)'),
    ('psa', 'PSA / Public Service'),
    ('news', 'News / Headline'),
    ('howto', 'How-To / Tip'),
    ('info', 'Info / Notice'),
]

COLOR_CHOICES = [
    ('danger', 'Red - Alert / Critical'),
    ('warning', 'Yellow / Orange - Warning'),
    ('info', 'Blue - Information'),
    ('success', 'Green - Positive / Tip'),
    ('primary', 'Brand Primary'),
    ('dark', 'Dark / Neutral'),
]


class PSABannerForm(FlaskForm):
    title = StringField('Headline / Title', validators=[
        DataRequired(),
        Length(min=5, max=200)
    ])
    content = TextAreaField('Body / Description (optional)', validators=[
        Optional(),
        Length(max=800)
    ])
    banner_type = SelectField('Type / Category', choices=BANNER_TYPE_CHOICES, default='info')
    color = SelectField('Color / Style', choices=COLOR_CHOICES, default='info')
    active = BooleanField('Active (shown to public)', default=True)
    priority = IntegerField('Priority (higher = shown first)', default=0, validators=[Optional(), NumberRange(min=-100, max=100)])
    link = StringField('Optional Link URL', validators=[Optional(), Length(max=500)], description="e.g. /listings/123 or https://...")
    expiry = DateTimeField('Expiry Date/Time (optional, UTC)', validators=[Optional()], format='%Y-%m-%d %H:%M', widget=DateTimeInput())
    submit = SubmitField('Save Banner')


class AdminListingForm(FlaskForm):
    """
    Full listing editor for authenticated admins.
    Covers all primary mutable fields on Listing (no schema change).
    - Uses DecimalField for price fields (precision) then cast to float for model.
    - Dynamic category choices populated in view.
    - Image uploads handled server-side (replace on new files provided).
    - CSRF via FlaskForm + hidden_tag.
    """
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=4000)])

    post_type = SelectField('Post Type', choices=POST_TYPE_CHOICES, validators=[DataRequired()])
    category = SelectField('Category', coerce=int, validators=[DataRequired()])

    price_type = SelectField('Price Type', choices=[
        ('fixed', 'Fixed Price'),
        ('range', 'Price Range (min – max)'),
        ('negotiable', 'Negotiable / Make Offer'),
        ('free', 'Free / Giveaway'),
    ], default='fixed', validators=[DataRequired()])

    price = DecimalField('Fixed Price (ZAR)', validators=[Optional(), NumberRange(min=0)], places=2)
    min_price = DecimalField('Min Price (ZAR)', validators=[Optional(), NumberRange(min=0)], places=2)
    max_price = DecimalField('Max Price (ZAR)', validators=[Optional(), NumberRange(min=0)], places=2)

    # VGS-002 multi-town
    town = SelectMultipleField(
        'Towns / Service Areas (select all that apply)',
        choices=TOWN_CHOICES,
        validators=[DataRequired(message="Please select at least one town or Klein Karoo region.")]
    )

    contact_phone = StringField('Contact Phone', validators=[Optional(), Length(max=20)])
    contact_email = StringField('Contact Email', validators=[Optional(), Length(max=120)])
    contact_methods = SelectMultipleField(
        'Contact Methods (how buyers can reach you)',
        choices=CONTACT_METHOD_CHOICES,
        validators=[DataRequired(message="Select at least one contact method.")],
        default=['dm', 'email', 'phone']
    )

    allow_comments = BooleanField('Allow comments on this listing', default=True)

    # Rental-only (shown/used when post_type=rental)
    rental_duration = IntegerField('Rental Duration', validators=[Optional(), NumberRange(min=1, max=365)])
    rental_duration_unit = SelectField('Rental Duration Unit', choices=[
        ('day', 'Day(s)'),
        ('week', 'Week(s)'),
        ('month', 'Month(s)')
    ], default='day', validators=[Optional()])

    # Core flags
    is_active = BooleanField('Active (visible to the public)', default=True)
    is_promoted = BooleanField('Promoted (shows "Promoted" badge)', default=False)
    is_business_ad = BooleanField('Business Ad', default=False)

    # Photos — new uploads REPLACE the current photo set (simple admin UX)
    photo = MultipleFileField('Photos (upload to replace current set)')

    # Admin can adjust expiry window directly
    expires_at = DateTimeField(
        'Expiry Date/Time (UTC, advanced)',
        validators=[Optional()],
        format='%Y-%m-%d %H:%M',
        widget=DateTimeInput()
    )

    submit = SubmitField('Save Full Listing Changes')
