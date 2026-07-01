from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional, URL, ValidationError
from flask_wtf.file import FileField, FileAllowed
from flask_login import current_user
from app.models.user import User


class ProfileForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    photo = FileField('Business Logo / Profile Picture', 
                      validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')])
    # Business upgrade fields (one-way, shown only for personal accounts)
    business_name = StringField('Business / Company Name', validators=[Optional(), Length(max=120)])
    business_type = StringField('Business Type / Category (optional)', validators=[Optional(), Length(max=80)])
    business_contact_person = StringField('Contact Person Name', validators=[Optional(), Length(max=100)])
    business_phone = StringField('Business Phone (for enquiries)', validators=[Optional(), Length(max=30)])

    # Business Profile Enhancement: website + social links (business accounts only)
    website = StringField('Website', validators=[Optional(), URL(message='Enter a valid URL including https://')])
    facebook = StringField('Facebook', validators=[Optional()])
    instagram = StringField('Instagram', validators=[Optional()])
    twitter = StringField('X/Twitter', validators=[Optional()])

    submit = SubmitField('Save Changes')

    def validate_email(self, field):
        if field.data != current_user.email:
            existing_user = User.query.filter_by(email=field.data).first()
            if existing_user:
                raise ValidationError('This email address is already in use by another account.')