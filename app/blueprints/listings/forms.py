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

    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=2000)])
    
    price_type = RadioField('Pricing', validators=[DataRequired()], choices=[
        ('fixed', '💰 Set Price'),
        ('range', '📏 Price Range')
    ], default='fixed')
    
    price = FloatField('Price (R)', validators=[Optional(), NumberRange(min=0)])
    min_price = FloatField('From (R)', validators=[Optional(), NumberRange(min=0)])
    max_price = FloatField('To (R)', validators=[Optional(), NumberRange(min=0)])
    
    town = SelectField('Town', coerce=str, validators=[DataRequired()], choices=[
        ('', 'Select a town...'),
        ('Barrydale', 'Barrydale'),
        ('Calitzdorp', 'Calitzdorp'),
        ('De Rust', 'De Rust'),
        ('Dysselsdorp', 'Dysselsdorp'),
        ('Groenfontein', 'Groenfontein'),
        ('Ladismith', 'Ladismith'),
        ('Oudtshoorn', 'Oudtshoorn'),
        ('Van Wyksdorp', 'Van Wyksdorp'),
        ('Zoar', 'Zoar')
    ])
    
    contact_preference = RadioField('How would you like to be contacted?', validators=[DataRequired()], choices=[
        ('email', '📧 Email only'),
        ('phone', '📞 Phone only'),
        ('dm', '📩 DM only (Premium)'),
        ('any', '🌐 Any (Phone + Email + DM)')
    ])
    
    allow_comments = BooleanField('Allow comments on this listing', default=True)
    
    contact_phone = StringField('Contact Phone')
    contact_email = StringField('Contact Email')
    category = SelectField('Category', coerce=int, validators=[DataRequired()])
    photo = FileField('Photo (optional)')
    submit = SubmitField('Create Listing')