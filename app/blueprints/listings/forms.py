from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FloatField, SelectField, FileField
from wtforms.validators import DataRequired, Length, NumberRange, Optional
from app.models.category import Category

class ListingForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = FloatField('Price (R)', validators=[DataRequired(), NumberRange(min=1)])
    location = StringField('Location', validators=[DataRequired()])
    area = StringField('Area', validators=[DataRequired()], default="Klein Karoo")
    contact_phone = StringField('Phone Number', validators=[Optional()])
    contact_email = StringField('Email', validators=[Optional()])
    
    # Category dropdown
    category = SelectField('Category', coerce=int, validators=[DataRequired()])
    
    photo = FileField('Photo (optional)')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate categories dynamically
        self.category.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
        
        # If no categories exist, add a helpful message
        if not self.category.choices:
            self.category.choices = [(-1, "No categories yet - please create one first")]