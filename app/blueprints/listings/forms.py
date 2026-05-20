from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FloatField, SelectField, FileField, SubmitField, RadioField
from wtforms.validators import DataRequired, Length, NumberRange

class ListingForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=2000)])
    price = FloatField('Price (R)', validators=[DataRequired(), NumberRange(min=0)])
    
    # New Town dropdown (Klein Karoo / ostrich country)
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
    
    # Contact preference (4 options, DM Only = premium)
    contact_preference = RadioField('Contact Preference', validators=[DataRequired()], choices=[
        ('dm_only', '📩 DM Only (Premium feature)'),
        ('phone', '📞 Phone only'),
        ('phone_email', '📞 Phone and Email'),
        ('all', '📞 Phone, Email and DM')
    ])
    
    contact_phone = StringField('Contact Phone')
    contact_email = StringField('Contact Email')
    category = SelectField('Category', coerce=int, validators=[DataRequired()])
    photo = FileField('Photo (optional)')
    submit = SubmitField('Create Listing')