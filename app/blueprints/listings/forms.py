from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length

class ListingForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = DecimalField('Price (R)', validators=[DataRequired()])
    area = SelectField('Area', choices=[
        ('Oudtshoorn', 'Oudtshoorn'),
        ('Calitzdorp', 'Calitzdorp'),
        ('Ladismith', 'Ladismith'),
        ('Van Wyksdorp', 'Van Wyksdorp'),
        ('Zoar', 'Zoar')
    ], validators=[DataRequired()])
    submit = SubmitField('Post Ad')