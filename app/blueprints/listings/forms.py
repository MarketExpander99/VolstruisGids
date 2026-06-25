from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, FloatField, SelectField, 
    FileField, MultipleFileField, SubmitField, RadioField, 
    BooleanField, IntegerField, SelectMultipleField
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


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
    town = SelectField('Town', validators=[DataRequired()], choices=[
        ('', 'Select a town...'),
        ('Calitzdorp', 'Calitzdorp'),
        ('Cape Town', 'Cape Town'),
        ('De Rust', 'De Rust'),
        ('Dysselsdorp', 'Dysselsdorp'),
        ('George', 'George'),
        ('Groenfontein', 'Groenfontein'),
        ('Ladismith', 'Ladismith'),
        ('Mossel Bay', 'Mossel Bay'),
        ('Oudtshoorn', 'Oudtshoorn'),
        ('Van Wyksdorp', 'Van Wyksdorp'),
        ('Zoar', 'Zoar')
    ])

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
