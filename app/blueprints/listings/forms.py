from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FloatField, SelectField, FileField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange

class ListingForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=2000)])
    price = FloatField('Price (R)', validators=[DataRequired(), NumberRange(min=0)])
    location = StringField('Location', validators=[DataRequired()])
    area = StringField('Area', validators=[DataRequired()])
    contact_phone = StringField('Contact Phone')
    contact_email = StringField('Contact Email')
    category = SelectField('Category', coerce=int, validators=[DataRequired()])
    photo = FileField('Photo (optional)')
    submit = SubmitField('Create Listing')   # ← this was missing