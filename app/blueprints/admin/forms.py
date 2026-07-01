from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DecimalField, TextAreaField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, Regexp


class UserSearchForm(FlaskForm):
    q = StringField('Search username or email', validators=[Optional(), Length(max=120)])
    submit = SubmitField('Search')


class UsernameChangeForm(FlaskForm):
    new_username = StringField('New Username', validators=[
        DataRequired(),
        Length(min=3, max=30),
        Regexp(r'^@?[a-zA-Z0-9_-]+$', message="Username can only contain letters, numbers, underscores and hyphens (leading @ is allowed but will be ignored).")
    ])
    submit = SubmitField('Change Username')

    def validate_new_username(self, field):
        if field.data:
            field.data = field.data.strip().lstrip('@')


class PasswordResetForm(FlaskForm):
    # No input needed — we generate secure temp password server-side
    confirm = HiddenField('confirm', default='yes')
    submit = SubmitField('Generate & Set Temporary Password')


class CreditAdjustForm(FlaskForm):
    amount = DecimalField('Amount (positive = add, negative = subtract)', validators=[DataRequired(), NumberRange(min=-10000, max=10000)], places=2)
    reason = StringField('Reason / Reference', validators=[DataRequired(), Length(min=3, max=200)])
    submit = SubmitField('Apply Credit Adjustment')


class ListingEditForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[DataRequired(), Length(max=2000)])
    submit = SubmitField('Save Changes')
