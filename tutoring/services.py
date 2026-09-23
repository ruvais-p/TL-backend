import logging
import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from curriculum.models import PublishStatus
from students.models import Enrollment
from accounts.admission import portal_admission
from accounts.constants import GroupName

from .grounding import build_grounded_prompt, select_context_chunks, validate_grounded_reply
from .models import (
    CourseChatMessage,
    CourseChatSession,
    CourseChatbotConfig,
    CourseSupportConversation,
    CourseSupportMessage,
    CourseSupportReadState,
    CourseSupportSocketTicket,
)
from .provider import MathTutorProviderError, ask_math_tutor
from .selectors import (
    active_course_enrollment,
    can_close_support_conversation,
    can_read_support_conversation,
    can_send_support_message,
    support_recipient_user_ids,
)

logger = logging.getLogger(__name__)


class ChatAccessError(Exception):
    pass


class ChatProviderUnavailable(Exception):
    pass


class SupportChatAccessError(Exception):
    pass


class SupportChatValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class SupportChatConflictError(Exception):
    pass


@dataclass(frozen=True)
class ChatResult:
    session_id: str
    reply: str
    grounded: bool
    citations: list[dict[str, str]]


@dataclass(frozen=True)
class SupportMessageResult:
    message: CourseSupportMessage
    created: bool


def save_chatbot_config(*, actor, instance=None, **data):
    if not actor.has_perm("tutoring.manage_course_chatbot"):
        raise PermissionError("Missing tutoring.manage_course_chatbot permission.")
    with transaction.atomic():
        if instance is None:
            config = CourseChatbotConfig(updated_by=actor, **data)
        else:
            config = CourseChatbotConfig.objects.select_for_update().get(pk=instance.pk)
            old_context = config.approved_context
            old_enabled = config.is_enabled
            for field, value in data.items():
                setattr(config, field, value)
            if config.approved_context != old_context or config.is_enabled != old_enabled:
                config.context_revision += 1
            config.updated_by = actor
        config.full_clean()
        config.save()
        if instance is not None and config.context_revision != instance.context_revision:
            CourseChatSession.objects.filter(course_version=config.course_version, is_active=True).update(is_active=False)
        return config


def _active_enrollment(*, student, course_id):
    return Enrollment.objects.select_related("course__program", "course_version").filter(
        student=student,
        course_id=course_id,
        status=Enrollment.Status.ACTIVE,
        course__status=PublishStatus.PUBLISHED,
        course__program__status=PublishStatus.PUBLISHED,
        course_version__status=PublishStatus.PUBLISHED,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).first()


def chatbot_available_for(*, student, course_id) -> bool:
    enrollment = _active_enrollment(student=student, course_id=course_id)
    if not enrollment:
        return False
    return CourseChatbotConfig.objects.filter(
        course_version=enrollment.course_version,
        is_enabled=True,
    ).exclude(approved_context="").exists()


@transaction.atomic
def get_or_create_support_conversation(*, student, course_id):
    enrollment = active_course_enrollment(student=student, course_id=course_id)
    if not enrollment:
        raise SupportChatAccessError
    try:
        with transaction.atomic():
            return CourseSupportConversation.objects.get_or_create(
                student=student,
                course_version=enrollment.course_version,
                defaults={"opened_from_enrollment": enrollment},
            )
    except IntegrityError:
        return (
            CourseSupportConversation.objects.get(
                student=student,
                course_version=enrollment.course_version,
            ),
            False,
        )


def _support_sender_role(user) -> str:
    if user.groups.filter(name=GroupName.STUDENT).exists():
        return CourseSupportMessage.SenderRole.STUDENT
    if user.groups.filter(name=GroupName.TEACHER).exists():
        return CourseSupportMessage.SenderRole.TEACHER
    if user.has_perm("tutoring.view_all_course_support_chats"):
        if user.groups.filter(name=GroupName.ACADEMIC_MANAGER).exists():
            return CourseSupportMessage.SenderRole.ACADEMIC_MANAGER
        return CourseSupportMessage.SenderRole.ADMIN
    return CourseSupportMessage.SenderRole.ADMIN


def _validate_support_content(content: str) -> str:
    normalized = content.strip()
    if not normalized:
        raise SupportChatValidationError("EMPTY_MESSAGE", "Message content cannot be empty.")
    max_chars = getattr(settings, "COURSE_SUPPORT_CHAT_MESSAGE_MAX_CHARS", 2000)
    if len(normalized) > max_chars:
        raise SupportChatValidationError(
            "MESSAGE_TOO_LONG",
            f"Message content cannot exceed {max_chars} characters.",
        )
    return normalized


@transaction.atomic
def send_support_message(*, actor, conversation_id, client_message_id: UUID, content: str) -> SupportMessageResult:
    normalized = _validate_support_content(content)
    conversation = CourseSupportConversation.objects.select_for_update().get(pk=conversation_id)
    if not can_send_support_message(user=actor, conversation=conversation):
        raise SupportChatAccessError

    existing = CourseSupportMessage.objects.filter(
        sender=actor,
        client_message_id=client_message_id,
    ).first()
    if existing:
        if existing.conversation_id != conversation.id:
            raise SupportChatConflictError("Client message identifier is already in use.")
        return SupportMessageResult(existing, False)

    is_student = actor.pk == conversation.student_id
    if conversation.status == CourseSupportConversation.Status.CLOSED and not is_student:
        raise SupportChatConflictError("Only an eligible learner message can reopen a closed conversation.")

    next_sequence = conversation.last_sequence + 1
    try:
        with transaction.atomic():
            message = CourseSupportMessage.objects.create(
                conversation=conversation,
                sender=actor,
                sender_role=_support_sender_role(actor),
                sequence=next_sequence,
                client_message_id=client_message_id,
                content=normalized,
            )
    except IntegrityError:
        duplicate = CourseSupportMessage.objects.filter(
            sender=actor,
            client_message_id=client_message_id,
        ).first()
        if duplicate and duplicate.conversation_id == conversation.id:
            return SupportMessageResult(duplicate, False)
        raise

    conversation.last_sequence = next_sequence
    conversation.last_message_at = message.created_at
    update_fields = ["last_sequence", "last_message_at", "updated_at"]
    if is_student and conversation.status == CourseSupportConversation.Status.CLOSED:
        conversation.status = CourseSupportConversation.Status.OPEN
        update_fields.append("status")
    conversation.save(update_fields=update_fields)
    from .events import publish_message_created

    transaction.on_commit(lambda: publish_message_created(message.id))
    return SupportMessageResult(message, True)


@transaction.atomic
def advance_support_read_state(*, actor, conversation_id, sequence: int):
    conversation = CourseSupportConversation.objects.select_for_update().get(pk=conversation_id)
    if not can_read_support_conversation(user=actor, conversation=conversation):
        raise SupportChatAccessError
    if sequence < 0 or sequence > conversation.last_sequence:
        raise SupportChatValidationError(
            "INVALID_SEQUENCE",
            "Read sequence must reference this conversation's durable history.",
        )
    state, _ = CourseSupportReadState.objects.select_for_update().get_or_create(
        conversation=conversation,
        user=actor,
    )
    if sequence > state.last_read_sequence:
        state.last_read_sequence = sequence
        state.save(update_fields=["last_read_sequence", "updated_at"])
        from .events import publish_read_updated

        transaction.on_commit(
            lambda: publish_read_updated(conversation.id, actor.id, state.last_read_sequence)
        )
    return state


@transaction.atomic
def close_support_conversation(*, actor, conversation_id):
    conversation = CourseSupportConversation.objects.select_for_update().get(pk=conversation_id)
    if not can_close_support_conversation(user=actor, conversation=conversation):
        raise SupportChatAccessError
    if conversation.status != CourseSupportConversation.Status.CLOSED:
        conversation.status = CourseSupportConversation.Status.CLOSED
        conversation.save(update_fields=["status", "updated_at"])
        from .events import publish_conversation_updated

        transaction.on_commit(lambda: publish_conversation_updated(conversation.id))
    return conversation


def current_support_recipient_user_ids(*, conversation) -> set:
    return support_recipient_user_ids(conversation)


def _socket_ticket_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def support_socket_portal_allowed(*, user, portal: str) -> bool:
    if not portal_admission(user, portal).allowed:
        return False
    if portal == CourseSupportSocketTicket.Portal.STAFF:
        return bool(
            user.has_perm("tutoring.reply_to_assigned_course_support_chats")
            or user.has_perm("tutoring.view_all_course_support_chats")
        )
    return portal == CourseSupportSocketTicket.Portal.LEARNER


def issue_support_socket_ticket(*, user, portal: str):
    if not getattr(settings, "COURSE_SUPPORT_CHAT_ENABLED", False):
        raise SupportChatAccessError
    if not support_socket_portal_allowed(user=user, portal=portal):
        raise SupportChatAccessError
    lifetime_seconds = getattr(settings, "COURSE_SUPPORT_CHAT_TICKET_TTL_SECONDS", 30)
    token = secrets.token_urlsafe(32)
    ticket = CourseSupportSocketTicket.objects.create(
        token_hash=_socket_ticket_hash(token),
        user=user,
        portal=portal,
        expires_at=timezone.now() + timedelta(seconds=lifetime_seconds),
    )
    return ticket, token


@transaction.atomic
def send_course_chat(*, student, course_id, message: str, session_id=None) -> ChatResult:
    enrollment = _active_enrollment(student=student, course_id=course_id)
    if not enrollment:
        raise ChatAccessError
    try:
        config = CourseChatbotConfig.objects.get(
            course_version=enrollment.course_version,
            is_enabled=True,
        )
    except CourseChatbotConfig.DoesNotExist as exc:
        raise ChatAccessError from exc
    if not config.approved_context.strip():
        raise ChatAccessError

    if session_id:
        try:
            session = CourseChatSession.objects.select_for_update().get(
                pk=session_id,
                student=student,
                course_version=enrollment.course_version,
                context_revision=config.context_revision,
                is_active=True,
            )
        except CourseChatSession.DoesNotExist as exc:
            raise ChatAccessError from exc
    else:
        session = CourseChatSession.objects.create(
            student=student,
            course_version=enrollment.course_version,
            context_revision=config.context_revision,
        )

    recent = list(session.messages.order_by("-created_at")[:settings.COURSE_CHAT_HISTORY_MESSAGES])
    history = [{"role": row.role, "content": row.content} for row in reversed(recent)]
    chunks = select_context_chunks(config.approved_context, message, history)

    grounded = False
    citations: list[dict[str, str]] = []
    reply = settings.COURSE_CHAT_REFUSAL
    if chunks:
        try:
            prompt = build_grounded_prompt(chunks, history, message)
            raw_reply = ask_math_tutor(prompt)
        except (MathTutorProviderError, ValueError) as exc:
            logger.warning(
                "course_chat_provider_failure session=%s version=%s code=%s",
                session.id,
                enrollment.course_version_id,
                getattr(exc, "code", "request_too_large"),
            )
            raise ChatProviderUnavailable from exc
        validated = validate_grounded_reply(raw_reply, chunks)
        if validated is not None:
            reply = validated.answer
            citations = validated.citations
            grounded = True

    CourseChatMessage.objects.create(session=session, role=CourseChatMessage.Role.USER, content=message)
    CourseChatMessage.objects.create(
        session=session,
        role=CourseChatMessage.Role.ASSISTANT,
        content=reply,
        citations=citations,
    )
    session.save(update_fields=["updated_at"])
    logger.info(
        "course_chat_complete session=%s version=%s grounded=%s chunks=%s",
        session.id,
        enrollment.course_version_id,
        grounded,
        ",".join(chunk.chunk_id for chunk in chunks),
    )
    return ChatResult(str(session.id), reply, grounded, citations)
