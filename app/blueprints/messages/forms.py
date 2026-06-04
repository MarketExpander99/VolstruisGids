from flask_wtf import FlaskForm
from wtforms import TextAreaField, HiddenField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class MessageForm(FlaskForm):
    """Simple form for sending/replying to private messages (MVP)."""
    text = TextAreaField(
        'Your Message',
        validators=[DataRequired(message="Message cannot be empty."), Length(min=1, max=2000)],
        render_kw={"rows": 3, "placeholder": "Type your message here... (keep it friendly and specific)", "class": "form-control"}
    )
    receiver_id = HiddenField(validators=[DataRequired()])
    listing_id = HiddenField(validators=[Optional()])
    submit = SubmitField('Send Message', render_kw={"class": "btn btn-primary"})
