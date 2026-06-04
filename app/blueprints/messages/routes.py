from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app import db
from app.models.message import Message
from app.models.user import User
from app.models.listing import Listing
from app.blueprints.messages import messages_bp
from .forms import MessageForm
from datetime import datetime


@messages_bp.route('/inbox')
@login_required
def inbox():
    """Show all conversations for the current user.
    A conversation is grouped by (other_user, listing).
    """
    # All messages where current user is sender or receiver
    user_messages = Message.query.filter(
        (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
    ).order_by(Message.timestamp.desc()).all()

    # Group into unique conversations (preserve order of most recent activity)
    from collections import OrderedDict
    conversations_dict = OrderedDict()

    for msg in user_messages:
        # Determine the other participant
        if msg.sender_id == current_user.id:
            other_id = msg.receiver_id
        else:
            other_id = msg.sender_id

        l_id = msg.listing_id or 0
        key = (other_id, l_id)

        if key not in conversations_dict:
            other_user = User.query.get(other_id)
            listing = Listing.query.get(l_id) if l_id else None

            conversations_dict[key] = {
                'other_user': other_user,
                'listing': listing,
                'last_message': msg,
                'unread_count': 0,
                'other_user_id': other_id,
                'listing_id': l_id,
            }

        # Count unread messages *to me* in this thread
        if msg.receiver_id == current_user.id and not msg.read:
            conversations_dict[key]['unread_count'] += 1

    conversations = list(conversations_dict.values())

    return render_template(
        'messages/inbox.html',
        conversations=conversations,
        title='Inbox'
    )


@messages_bp.route('/conversation/<int:other_user_id>/<int:listing_id>')
@login_required
def conversation(other_user_id, listing_id):
    """View full chronological thread with one person about one listing (or general if listing_id=0)."""
    other_user = User.query.get_or_404(other_user_id)

    if other_user.id == current_user.id:
        flash('You cannot message yourself.', 'danger')
        return redirect(url_for('messages.inbox'))

    listing = Listing.query.get(listing_id) if listing_id and listing_id > 0 else None

    # Fetch the full thread between these two users (optionally filtered to listing)
    thread_query = Message.query.filter(
        (
            (Message.sender_id == current_user.id) & (Message.receiver_id == other_user.id)
        ) | (
            (Message.sender_id == other_user.id) & (Message.receiver_id == current_user.id)
        )
    )

    if listing_id and listing_id > 0:
        thread_query = thread_query.filter(Message.listing_id == listing_id)

    messages = thread_query.order_by(Message.timestamp.asc()).all()

    # Mark messages sent *to me* as read
    mark_read = False
    for msg in messages:
        if msg.receiver_id == current_user.id and not msg.read:
            msg.read = True
            mark_read = True
    if mark_read:
        db.session.commit()

    form = MessageForm()
    # Prefill so that {{ form.hidden_tag() }} could include them if desired; manual hiddens also present for robustness
    form.receiver_id.data = other_user_id
    form.listing_id.data = listing_id or 0

    return render_template(
        'messages/conversation.html',
        other_user=other_user,
        listing=listing,
        messages=messages,
        form=form,
        other_user_id=other_user_id,
        listing_id=listing_id or 0,
        title=f'Chat with {other_user.username}'
    )


@messages_bp.route('/send', methods=['POST'])
@login_required
def send_message():
    """Handle sending a new message (from detail page or from conversation reply).
    Always redirects back to the relevant conversation.
    """
    form = MessageForm()

    if form.validate_on_submit():
        try:
            receiver_id = int(form.receiver_id.data)
            listing_id_raw = form.listing_id.data
            listing_id = int(listing_id_raw) if listing_id_raw and str(listing_id_raw).strip() and int(listing_id_raw) > 0 else None
            text = (form.text.data or '').strip()

            if not text:
                flash('Message cannot be empty.', 'danger')
                return redirect(request.referrer or url_for('messages.inbox'))

            receiver = User.query.get(receiver_id)
            if not receiver:
                flash('Recipient not found.', 'danger')
                return redirect(url_for('messages.inbox'))

            if receiver.id == current_user.id:
                flash('You cannot send a message to yourself.', 'danger')
                return redirect(url_for('messages.inbox'))

            # Create and persist message (linked to listing when provided)
            new_message = Message(
                sender_id=current_user.id,
                receiver_id=receiver.id,
                listing_id=listing_id,
                text=text,
                read=False,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_message)
            db.session.commit()

            flash('✅ Message sent successfully!', 'success')

            # Redirect to the conversation view
            target_listing_id = listing_id or 0
            return redirect(url_for(
                'messages.conversation',
                other_user_id=receiver.id,
                listing_id=target_listing_id
            ))

        except (ValueError, TypeError) as e:
            flash('Invalid message data. Please try again.', 'danger')
            return redirect(request.referrer or url_for('messages.inbox'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error sending message: {str(e)}', 'danger')
            return redirect(request.referrer or url_for('messages.inbox'))

    # Form validation failed
    for field, errors in form.errors.items():
        for error in errors:
            flash(f'{field}: {error}', 'danger')

    return redirect(request.referrer or url_for('messages.inbox'))


# Optional convenience redirect for /messages/
@messages_bp.route('/')
@login_required
def messages_root():
    return redirect(url_for('messages.inbox'))
