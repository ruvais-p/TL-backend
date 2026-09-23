import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from curriculum.models import CourseVersion
from students.models import Enrollment


class TimestampedUUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CourseChatbotConfig(TimestampedUUIDModel):
    course_version = models.OneToOneField(
        CourseVersion, on_delete=models.CASCADE, related_name="chatbot_config"
    )
    is_enabled = models.BooleanField(default=False, db_index=True)
    approved_context = models.TextField(blank=True)
    context_revision = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chatbot_configs_updated",
    )

    class Meta:
        ordering = ["course_version__course__name", "-course_version__version_number"]
        permissions = [("manage_course_chatbot", "Can manage course chatbot configuration")]

    def clean(self):
        if self.is_enabled and not self.approved_context.strip():
            raise ValidationError({"approved_context": "Approved context is required before enabling the chatbot."})


class CourseChatSession(TimestampedUUIDModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="course_chat_sessions"
    )
    course_version = models.ForeignKey(
        CourseVersion, on_delete=models.PROTECT, related_name="chat_sessions"
    )
    context_revision = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["student", "course_version", "is_active"], name="chat_sess_student_ver_idx"),
        ]


class CourseChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "USER", "User"
        ASSISTANT = "ASSISTANT", "Assistant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(CourseChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["session", "created_at"], name="chat_msg_session_created_idx")]


class CourseSupportConversation(TimestampedUUIDModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="course_support_conversations",
    )
    course_version = models.ForeignKey(
        CourseVersion,
        on_delete=models.PROTECT,
        related_name="support_conversations",
    )
    opened_from_enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.PROTECT,
        related_name="support_conversations_opened",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    last_sequence = models.PositiveBigIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course_version"],
                name="unique_student_course_support_conversation",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "course_version"], name="support_conv_student_ver_idx"),
            models.Index(fields=["status", "last_message_at"], name="support_conv_status_recent_idx"),
        ]
        permissions = [
            ("reply_to_assigned_course_support_chats", "Can reply to assigned course support chats"),
            ("view_all_course_support_chats", "Can view all course support chats"),
            ("close_course_support_chats", "Can close course support chats"),
        ]


class CourseSupportMessage(models.Model):
    class SenderRole(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        TEACHER = "TEACHER", "Teacher"
        ACADEMIC_MANAGER = "ACADEMIC_MANAGER", "Academic manager"
        ADMIN = "ADMIN", "Administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        CourseSupportConversation,
        on_delete=models.CASCADE,
        related_name="support_messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="course_support_messages",
    )
    sender_role = models.CharField(max_length=24, choices=SenderRole.choices)
    sequence = models.PositiveBigIntegerField()
    client_message_id = models.UUIDField()
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "sequence"],
                name="unique_support_message_sequence",
            ),
            models.UniqueConstraint(
                fields=["sender", "client_message_id"],
                name="unique_support_sender_client_message",
            ),
        ]
        indexes = [
            models.Index(fields=["conversation", "sequence"], name="support_msg_conv_seq_idx"),
        ]


class CourseSupportReadState(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        CourseSupportConversation,
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_support_read_states",
    )
    last_read_sequence = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"],
                name="unique_support_read_state",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "conversation"], name="support_read_user_conv_idx"),
        ]


class CourseSupportSocketTicket(models.Model):
    class Portal(models.TextChoices):
        STAFF = "staff", "Staff"
        LEARNER = "learner", "Learner"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_support_socket_tickets",
    )
    portal = models.CharField(max_length=12, choices=Portal.choices)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["expires_at", "consumed_at"], name="support_ticket_expiry_idx"),
        ]
