from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from accounts.permissions import IsStudent

from . import services
from .models import CourseChatbotConfig, CourseSupportConversation
from .permissions import CanManageCourseChatbot
from .selectors import active_course_enrollment, visible_support_conversations
from .serializers import (
    CourseChatRequestSerializer,
    CourseChatbotConfigSerializer,
    CourseSupportConversationSerializer,
    CourseSupportMessageSerializer,
    CourseSupportReadSerializer,
    CourseSupportSocketTicketRequestSerializer,
)


class CourseChatThrottle(UserRateThrottle):
    scope = "course_chat"


class CourseChatbotConfigViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, CanManageCourseChatbot]
    serializer_class = CourseChatbotConfigSerializer
    queryset = CourseChatbotConfig.objects.select_related("course_version", "updated_by")

    def get_queryset(self):
        queryset = super().get_queryset()
        if course_version := self.request.query_params.get("course_version"):
            queryset = queryset.filter(course_version_id=course_version)
        return queryset

    def perform_create(self, serializer):
        serializer.instance = services.save_chatbot_config(actor=self.request.user, **serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = services.save_chatbot_config(
            actor=self.request.user, instance=self.get_object(), **serializer.validated_data
        )


class CourseChatView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]
    throttle_classes = [CourseChatThrottle]

    def post(self, request, course_id):
        serializer = CourseChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = services.send_course_chat(
                student=request.user,
                course_id=course_id,
                message=serializer.validated_data["message"],
                session_id=serializer.validated_data.get("session_id"),
            )
        except services.ChatAccessError:
            return Response({"detail": "Course chatbot not found."}, status=status.HTTP_404_NOT_FOUND)
        except services.ChatProviderUnavailable:
            return Response(
                {"error": {"code": "TUTOR_UNAVAILABLE", "message": "Tutor temporarily unavailable.", "details": {}}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({
            "session_id": result.session_id,
            "reply": result.reply,
            "grounded": result.grounded,
            "citations": result.citations,
        })


class SupportChatEnabledMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(settings, "COURSE_SUPPORT_CHAT_ENABLED", False):
            raise NotFound


class SupportConversationCursorPagination(CursorPagination):
    page_size = settings.COURSE_SUPPORT_CHAT_HISTORY_PAGE_SIZE
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = ("-last_message_at", "-created_at", "-id")


class LearnerSupportConversationView(SupportChatEnabledMixin, APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, course_id):
        enrollment = active_course_enrollment(student=request.user, course_id=course_id)
        conversation = CourseSupportConversation.objects.select_related(
            "student", "course_version__course"
        ).filter(student=request.user, course_version__course_id=course_id).first()
        return Response({
            "available": enrollment is not None,
            "conversation": (
                CourseSupportConversationSerializer(conversation, context={"request": request}).data
                if conversation else None
            ),
        })

    def post(self, request, course_id):
        try:
            conversation, created = services.get_or_create_support_conversation(
                student=request.user,
                course_id=course_id,
            )
        except services.SupportChatAccessError:
            return Response({"detail": "Course support is unavailable."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CourseSupportConversationSerializer(conversation, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class StaffSupportConversationListView(SupportChatEnabledMixin, APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = SupportConversationCursorPagination

    def get(self, request):
        if not (
            request.user.has_perm("tutoring.reply_to_assigned_course_support_chats")
            or request.user.has_perm("tutoring.view_all_course_support_chats")
        ):
            return Response({"detail": "You do not have permission to perform this action."}, status=403)
        queryset = visible_support_conversations(request.user)
        if value := request.query_params.get("status"):
            queryset = queryset.filter(status=value.upper())
        if value := request.query_params.get("course"):
            queryset = queryset.filter(course_version__course_id=value)
        if value := request.query_params.get("group"):
            queryset = queryset.filter(
                student__student_group_memberships__student_group_id=value,
                course_version__assignments__student_group_id=value,
                course_version__assignments__status="ACTIVE",
            ).distinct()
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CourseSupportConversationSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class SupportConversationMessagesView(SupportChatEnabledMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conversation = get_object_or_404(visible_support_conversations(request.user), pk=conversation_id)
        try:
            after_sequence = int(request.query_params.get("after_sequence", 0))
            limit = min(
                int(request.query_params.get("limit", settings.COURSE_SUPPORT_CHAT_HISTORY_PAGE_SIZE)),
                100,
            )
        except ValueError:
            return Response({"detail": "Invalid recovery cursor."}, status=400)
        if after_sequence < 0 or limit < 1:
            return Response({"detail": "Invalid recovery cursor."}, status=400)
        rows = list(
            conversation.support_messages.select_related("sender")
            .filter(sequence__gt=after_sequence)
            .order_by("sequence")[: limit + 1]
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        return Response({
            "results": CourseSupportMessageSerializer(rows, many=True).data,
            "has_more": has_more,
            "next_after_sequence": rows[-1].sequence if rows else after_sequence,
        })


class SupportConversationReadView(SupportChatEnabledMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        serializer = CourseSupportReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            state = services.advance_support_read_state(
                actor=request.user,
                conversation_id=conversation_id,
                sequence=serializer.validated_data["sequence"],
            )
        except CourseSupportConversation.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)
        except services.SupportChatAccessError:
            return Response({"detail": "Not found."}, status=404)
        except services.SupportChatValidationError as exc:
            return Response({"error": {"code": exc.code, "message": str(exc), "details": {}}}, status=400)
        return Response({"conversation_id": str(conversation_id), "sequence": state.last_read_sequence})


class SupportConversationCloseView(SupportChatEnabledMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        try:
            conversation = services.close_support_conversation(
                actor=request.user,
                conversation_id=conversation_id,
            )
        except (CourseSupportConversation.DoesNotExist, services.SupportChatAccessError):
            return Response({"detail": "Not found."}, status=404)
        return Response(CourseSupportConversationSerializer(conversation, context={"request": request}).data)


class SupportSocketTicketView(SupportChatEnabledMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CourseSupportSocketTicketRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket, token = services.issue_support_socket_ticket(
                user=request.user,
                portal=serializer.validated_data["portal"],
            )
        except services.SupportChatAccessError:
            return Response({"detail": "You do not have permission to perform this action."}, status=403)
        return Response({
            "ticket": token,
            "expires_at": ticket.expires_at,
            "websocket_url": settings.COURSE_SUPPORT_CHAT_WEBSOCKET_URL,
        }, status=201)
