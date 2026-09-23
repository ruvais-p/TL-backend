from django.conf import settings
from rest_framework import serializers

from students.models import CourseAssignment, StudentGroup

from .models import (
    CourseChatbotConfig,
    CourseSupportConversation,
    CourseSupportMessage,
    CourseSupportSocketTicket,
)
from .selectors import can_close_support_conversation, can_send_support_message


class CourseChatbotConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseChatbotConfig
        fields = (
            "id", "course_version", "is_enabled", "approved_context", "context_revision",
            "updated_by", "created_at", "updated_at",
        )
        read_only_fields = ("context_revision", "updated_by", "created_at", "updated_at")

    def validate_approved_context(self, value):
        if len(value) > settings.COURSE_CHAT_CONTEXT_MAX_CHARS:
            raise serializers.ValidationError(
                f"Approved context cannot exceed {settings.COURSE_CHAT_CONTEXT_MAX_CHARS} characters."
            )
        return value.strip()

    def validate(self, attrs):
        current_context = self.instance.approved_context if self.instance else ""
        current_enabled = self.instance.is_enabled if self.instance else False
        context = attrs.get("approved_context", current_context)
        enabled = attrs.get("is_enabled", current_enabled)
        if enabled and not context.strip():
            raise serializers.ValidationError({"approved_context": "Approved context is required before enabling the chatbot."})
        return attrs


class CourseChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(trim_whitespace=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_message(self, value):
        if len(value) > settings.COURSE_CHAT_MESSAGE_MAX_CHARS:
            raise serializers.ValidationError(
                f"Message cannot exceed {settings.COURSE_CHAT_MESSAGE_MAX_CHARS} characters."
            )
        return value


class CourseSupportMessageSerializer(serializers.ModelSerializer):
    sender = serializers.SerializerMethodField()

    class Meta:
        model = CourseSupportMessage
        fields = (
            "id", "conversation", "sender", "sender_role", "sequence",
            "client_message_id", "content", "created_at",
        )

    def get_sender(self, obj):
        return {
            "id": str(obj.sender_id),
            "email": obj.sender.email,
            "first_name": obj.sender.first_name,
            "last_name": obj.sender.last_name,
        }


class CourseSupportConversationSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()
    course = serializers.SerializerMethodField()
    course_version = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    can_send = serializers.SerializerMethodField()
    can_close = serializers.SerializerMethodField()

    class Meta:
        model = CourseSupportConversation
        fields = (
            "id", "student", "course", "course_version", "groups", "status",
            "last_sequence", "last_message_at", "last_message", "unread_count",
            "can_send", "can_close", "created_at", "updated_at",
        )

    def get_student(self, obj):
        return {
            "id": str(obj.student_id),
            "email": obj.student.email,
            "first_name": obj.student.first_name,
            "last_name": obj.student.last_name,
        }

    def get_course(self, obj):
        course = obj.course_version.course
        return {"id": str(course.id), "name": course.name, "code": course.code}

    def get_course_version(self, obj):
        return {
            "id": str(obj.course_version_id),
            "name": obj.course_version.name,
            "version_number": obj.course_version.version_number,
        }

    def get_groups(self, obj):
        return list(
            StudentGroup.objects.filter(
                status=StudentGroup.Status.ACTIVE,
                memberships__student_id=obj.student_id,
                course_assignments__course_version_id=obj.course_version_id,
                course_assignments__status=CourseAssignment.Status.ACTIVE,
            ).values("id", "name", "code").distinct()
        )

    def get_last_message(self, obj):
        message = obj.support_messages.select_related("sender").order_by("-sequence").first()
        return CourseSupportMessageSerializer(message).data if message else None

    def get_unread_count(self, obj):
        actor = self.context["request"].user
        state = obj.read_states.filter(user=actor).first()
        return max(0, obj.last_sequence - (state.last_read_sequence if state else 0))

    def get_can_send(self, obj):
        return can_send_support_message(user=self.context["request"].user, conversation=obj)

    def get_can_close(self, obj):
        return can_close_support_conversation(user=self.context["request"].user, conversation=obj)


class CourseSupportReadSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=0)


class CourseSupportSocketTicketRequestSerializer(serializers.Serializer):
    portal = serializers.ChoiceField(choices=CourseSupportSocketTicket.Portal.choices)
