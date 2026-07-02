from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DecimalField, TextAreaField, SubmitField, HiddenField, SelectField, BooleanField, DateTimeField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, Regexp
from wtforms.widgets import DateTimeInput  # for expiry input


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
