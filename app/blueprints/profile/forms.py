from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from flask_login import current_user
from app.models.user import User


class ProfileForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Save Changes')

    def validate_email(self, field):
        if field.data != current_user.email:
            existing_user = User.query.filter_by(email=field.data).first()
            if existing_user:
                raise ValidationError('This email address is already in use by another account.')