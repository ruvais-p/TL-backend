import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import CourseSupportConversation, CourseSupportMessage
from .selectors import support_recipient_user_ids

logger = logging.getLogger(__name__)


def support_user_group_name(user_id) -> str:
    return f"course_support.user.{user_id}"


def serialize_support_message(message):
    return {
        "id": str(message.id),
        "conversation": str(message.conversation_id),
        "sender": {
            "id": str(message.sender_id),
            "email": message.sender.email,
            "first_name": message.sender.first_name,
            "last_name": message.sender.last_name,
        },
        "sender_role": message.sender_role,
        "sequence": message.sequence,
        "client_message_id": str(message.client_message_id),
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def serialize_support_conversation_event(conversation):
    return {
        "id": str(conversation.id),
        "status": conversation.status,
        "last_sequence": conversation.last_sequence,
        "last_message_at": (
            conversation.last_message_at.isoformat() if conversation.last_message_at else None
        ),
        "updated_at": conversation.updated_at.isoformat(),
    }


def _send_to_user_ids(user_ids, payload):
    channel_layer = get_channel_layer()
    for user_id in user_ids:
        try:
            async_to_sync(channel_layer.group_send)(
                support_user_group_name(user_id),
                {"type": "support.event", "payload": payload},
            )
        except Exception:
            logger.exception(
                "course_support_delivery_failed event_type=%s user_id=%s conversation_id=%s",
                payload.get("type"),
                user_id,
                payload.get("conversation", {}).get("id") or payload.get("conversation_id"),
            )


def publish_message_created(message_id):
    message = CourseSupportMessage.objects.select_related("sender", "conversation").get(pk=message_id)
    conversation = message.conversation
    payload = {
        "v": 1,
        "type": "message.created",
        "conversation": serialize_support_conversation_event(conversation),
        "message": serialize_support_message(message),
    }
    _send_to_user_ids(support_recipient_user_ids(conversation), payload)


def publish_conversation_updated(conversation_id):
    conversation = CourseSupportConversation.objects.get(pk=conversation_id)
    payload = {
        "v": 1,
        "type": "conversation.updated",
        "conversation": serialize_support_conversation_event(conversation),
    }
    _send_to_user_ids(support_recipient_user_ids(conversation), payload)


def publish_read_updated(conversation_id, user_id, sequence):
    payload = {
        "v": 1,
        "type": "conversation.read.updated",
        "conversation_id": str(conversation_id),
        "sequence": sequence,
    }
    _send_to_user_ids({user_id}, payload)
