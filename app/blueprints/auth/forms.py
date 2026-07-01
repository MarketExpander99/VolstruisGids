from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional, EqualTo, ValidationError, Regexp
from app.models.user import User


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=30),
        Regexp(r'^@?[a-zA-Z0-9_-]+$', message="Username can only contain letters, numbers, underscores and hyphens (leading @ is allowed but will be ignored).")
    ])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

    def validate_username(self, field):
        if field.data:
            field.data = field.data.strip().lstrip('@')


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=30),
        Regexp(r'^@?[a-zA-Z0-9_-]+$', message="Username can only contain letters, numbers, underscores and hyphens (leading @ is allowed but will be ignored).")
    ])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=20)])
    email = StringField('Email (optional)', validators=[Optional(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    is_business = BooleanField('Register as Business Account')
    business_name = StringField('Business / Company Name', validators=[Optional()])
    submit = SubmitField('Register')

    def validate_username(self, field):
        if field.data:
            field.data = field.data.strip().lstrip('@')

    def validate_email(self, field):
        if field.data:  # only check if email was provided
            existing_user = User.query.filter_by(email=field.data).first()
            if existing_user:
                raise ValidationError('This email address is already registered. Please use a different one or log in.')