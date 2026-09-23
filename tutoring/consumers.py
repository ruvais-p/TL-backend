import json
import logging
import time
from uuid import UUID

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.core.cache import cache

from . import services
from .events import serialize_support_conversation_event, serialize_support_message
from .models import CourseSupportConversation

logger = logging.getLogger(__name__)


def support_user_group_name(user_id) -> str:
    return f"course_support.user.{user_id}"


def _parse_rate(value):
    amount, unit = value.split("/", 1)
    seconds = {"sec": 1, "second": 1, "min": 60, "minute": 60, "hour": 3600}.get(unit)
    if seconds is None:
        raise ValueError(f"Unsupported rate period: {unit}")
    return int(amount), seconds


def _allow_rate(key_prefix, user_id, rate):
    limit, seconds = _parse_rate(rate)
    bucket = int(time.time() // seconds)
    key = f"course-support:{key_prefix}:{user_id}:{bucket}"
    cache.add(key, 0, timeout=seconds + 1)
    return cache.incr(key) <= limit


def _claim_connection(user_id):
    if not _allow_rate("connections", user_id, settings.COURSE_SUPPORT_CHAT_CONNECTION_RATE):
        return False
    key = f"course-support:active:{user_id}"
    cache.add(key, 0, timeout=3600)
    count = cache.incr(key)
    if count > settings.COURSE_SUPPORT_CHAT_MAX_CONNECTIONS_PER_USER:
        cache.decr(key)
        return False
    cache.touch(key, timeout=3600)
    return True


def _release_connection(user_id):
    key = f"course-support:active:{user_id}"
    value = cache.get(key, 0)
    if value <= 1:
        cache.delete(key)
    else:
        cache.decr(key)


_allow_rate_async = sync_to_async(_allow_rate, thread_sensitive=False)
_claim_connection_async = sync_to_async(_claim_connection, thread_sensitive=False)
_release_connection_async = sync_to_async(_release_connection, thread_sensitive=False)


@database_sync_to_async
def _send_message(actor, conversation_id, client_message_id, content):
    result = services.send_support_message(
        actor=actor,
        conversation_id=conversation_id,
        client_message_id=client_message_id,
        content=content,
    )
    return serialize_support_message(result.message), result.created


@database_sync_to_async
def _mark_read(actor, conversation_id, sequence):
    state = services.advance_support_read_state(
        actor=actor,
        conversation_id=conversation_id,
        sequence=sequence,
    )
    return state.last_read_sequence


@database_sync_to_async
def _close_conversation(actor, conversation_id):
    conversation = services.close_support_conversation(
        actor=actor,
        conversation_id=conversation_id,
    )
    return serialize_support_conversation_event(conversation)


class CourseSupportConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.connection_claimed = await _claim_connection_async(self.scope["user"].pk)
        if not self.connection_claimed:
            await self.close(code=4429)
            return
        self.user_group = support_user_group_name(self.scope["user"].pk)
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if getattr(self, "connection_claimed", False):
            await _release_connection_async(self.scope["user"].pk)

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if bytes_data is not None:
            await self._error(None, "BINARY_NOT_SUPPORTED", "Binary frames are not supported.")
            return
        if text_data is None:
            return
        if len(text_data.encode("utf-8")) > settings.COURSE_SUPPORT_CHAT_EVENT_MAX_BYTES:
            await self._error(None, "FRAME_TOO_LARGE", "The event exceeds the configured size limit.")
            return
        try:
            content = json.loads(text_data)
        except (TypeError, ValueError):
            await self._error(None, "INVALID_JSON", "The event must be valid JSON.")
            return
        await self.receive_json(content)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self._error(None, "INVALID_EVENT", "The event must be a JSON object.")
            return
        request_id = content.get("request_id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 100:
            await self._error(None, "INVALID_REQUEST_ID", "A bounded request_id is required.")
            return
        if content.get("v") != 1:
            await self._error(request_id, "UNSUPPORTED_VERSION", "Only protocol version 1 is supported.")
            return
        event_type = content.get("type")
        handlers = {
            "message.send": self._handle_message_send,
            "conversation.read": self._handle_conversation_read,
            "conversation.close": self._handle_conversation_close,
        }
        handler = handlers.get(event_type)
        if handler is None:
            await self._error(request_id, "UNKNOWN_TYPE", "Unknown event type.")
            return
        await handler(request_id, content)

    async def _handle_message_send(self, request_id, content):
        if set(content) != {"v", "request_id", "type", "conversation_id", "client_message_id", "content"}:
            await self._error(request_id, "INVALID_EVENT", "Unexpected or missing event fields.")
            return
        try:
            conversation_id = UUID(str(content["conversation_id"]))
            client_message_id = UUID(str(content["client_message_id"]))
        except (TypeError, ValueError):
            await self._error(request_id, "INVALID_IDENTIFIER", "Conversation and client message identifiers must be UUIDs.")
            return
        if not isinstance(content["content"], str):
            await self._error(request_id, "INVALID_CONTENT", "Message content must be text.")
            return
        allowed = await _allow_rate_async(
            "send", self.scope["user"].pk, settings.COURSE_SUPPORT_CHAT_SEND_RATE
        )
        if not allowed:
            await self._error(request_id, "RATE_LIMITED", "Message rate limit exceeded.")
            return
        try:
            message, created = await _send_message(
                self.scope["user"], conversation_id, client_message_id, content["content"]
            )
        except CourseSupportConversation.DoesNotExist:
            await self._error(request_id, "NOT_FOUND", "Conversation not found.")
            return
        except services.SupportChatAccessError:
            await self._error(request_id, "FORBIDDEN", "Conversation access is no longer available.")
            return
        except services.SupportChatValidationError as exc:
            await self._error(request_id, exc.code, str(exc))
            return
        except services.SupportChatConflictError as exc:
            await self._error(request_id, "CONFLICT", str(exc))
            return
        await self.send_json({
            "v": 1,
            "request_id": request_id,
            "type": "message.accepted",
            "created": created,
            "message": message,
        })

    async def _handle_conversation_read(self, request_id, content):
        if set(content) != {"v", "request_id", "type", "conversation_id", "sequence"}:
            await self._error(request_id, "INVALID_EVENT", "Unexpected or missing event fields.")
            return
        try:
            conversation_id = UUID(str(content["conversation_id"]))
        except (TypeError, ValueError):
            await self._error(request_id, "INVALID_IDENTIFIER", "Conversation identifier must be a UUID.")
            return
        sequence = content["sequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            await self._error(request_id, "INVALID_SEQUENCE", "Sequence must be a non-negative integer.")
            return
        try:
            stored_sequence = await _mark_read(self.scope["user"], conversation_id, sequence)
        except (CourseSupportConversation.DoesNotExist, services.SupportChatAccessError):
            await self._error(request_id, "NOT_FOUND", "Conversation not found.")
            return
        except services.SupportChatValidationError as exc:
            await self._error(request_id, exc.code, str(exc))
            return
        await self.send_json({
            "v": 1,
            "request_id": request_id,
            "type": "conversation.read.accepted",
            "conversation_id": str(conversation_id),
            "sequence": stored_sequence,
        })

    async def _handle_conversation_close(self, request_id, content):
        if set(content) != {"v", "request_id", "type", "conversation_id"}:
            await self._error(request_id, "INVALID_EVENT", "Unexpected or missing event fields.")
            return
        try:
            conversation_id = UUID(str(content["conversation_id"]))
        except (TypeError, ValueError):
            await self._error(request_id, "INVALID_IDENTIFIER", "Conversation identifier must be a UUID.")
            return
        try:
            conversation = await _close_conversation(self.scope["user"], conversation_id)
        except (CourseSupportConversation.DoesNotExist, services.SupportChatAccessError):
            await self._error(request_id, "NOT_FOUND", "Conversation not found.")
            return
        await self.send_json({
            "v": 1,
            "request_id": request_id,
            "type": "conversation.close.accepted",
            "conversation": conversation,
        })

    async def support_event(self, event):
        await self.send_json(event["payload"])

    async def _error(self, request_id, code, message):
        logger.info(
            "course_support_command_rejected user_id=%s request_id=%s code=%s",
            self.scope["user"].pk,
            request_id,
            code,
        )
        await self.send_json({
            "v": 1,
            "request_id": request_id,
            "type": "error",
            "error": {"code": code, "message": message, "details": {}},
        })
