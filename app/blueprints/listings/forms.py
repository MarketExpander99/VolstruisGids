from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FloatField, SelectField, FileField, SubmitField, RadioField, BooleanField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class ListingForm(FlaskForm):
    post_type = RadioField('Post Type', validators=[DataRequired()], choices=[
        ('sale', '🛒 Items for Sale'),
        ('wanted', '🔍 Looking for'),
        ('services', '🛠 Services Offered'),
        ('announcement', '📢 General Announcement')
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
        ('De Rust', 'De Rust'),
        ('Dysselsdorp', 'Dysselsdorp'),
        ('Groenfontein', 'Groenfontein'),
        ('Ladismith', 'Ladismith'),
        ('Oudtshoorn', 'Oudtshoorn'),
        ('Van Wyksdorp', 'Van Wyksdorp'),
        ('Zoar', 'Zoar')
    ])

    # Contact preference - DM removed for now (frontend only)
    contact_preference = RadioField('How would you like to be contacted?', validators=[DataRequired()], choices=[
        ('email', '📧 Email only'),
        ('phone', '📞 Phone only'),
        ('any', '🌐 Any (Phone + Email)')
    ], default='any')

    allow_comments = BooleanField('Allow comments on this listing', default=True)

    contact_phone = StringField('Contact Phone')
    contact_email = StringField('Contact Email')

    photo = FileField('Photo (optional)')