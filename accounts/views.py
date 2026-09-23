import hashlib
import hmac
import time
import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from rest_framework import status
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import CanManagePermissions, CanManageUsers, active_permission_queryset
from .serializers import (
    Auth0ExchangeSerializer,
    EmailTokenObtainPairSerializer,
    ManagedUserSerializer,
    PermissionSerializer,
    RolePermissionsSerializer,
    RoleSerializer,
    UserSerializer,
)
from .constants import GroupName
from .models import User
from .admission import portal_admission
from .auth0 import Auth0AdmissionError, Auth0VerificationError, exchange_auth0_assertion
from students.models import ExternalUserMapping


class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


def token_pair_for_user(user, auth_method: str):
    refresh = RefreshToken.for_user(user)
    refresh["email"] = user.email
    refresh["groups"] = list(user.groups.values_list("name", flat=True))
    refresh["auth_method"] = auth_method
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class Auth0ExchangeView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth0_exchange"

    def post(self, request):
        serializer = Auth0ExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        try:
            user = exchange_auth0_assertion(
                serializer.validated_data["assertion"],
                correlation_id=correlation_id,
            )
        except Auth0VerificationError:
            return Response(
                {"detail": "Unable to complete sign in."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Auth0AdmissionError:
            return Response(
                {"detail": "This account cannot access the requested workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not portal_admission(user, serializer.validated_data["portal"]).allowed:
            return Response(
                {"detail": "This account cannot access the requested workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({
            **token_pair_for_user(user, "auth0"),
            "user": UserSerializer(user).data,
        })


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": {"code": "REFRESH_TOKEN_REQUIRED", "message": "Refresh token is required.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            return Response(
                {"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Refresh token is invalid or expired.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MoodleExchangeView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        external_id = str(request.data.get("moodle_user_id") or "").strip()
        email = str(request.data.get("email") or "").strip().lower()
        signature = str(request.data.get("signature") or "")
        try:
            timestamp = int(request.data.get("timestamp"))
        except (TypeError, ValueError):
            timestamp = 0
        if not external_id or not email or not signature or abs(time.time() - timestamp) > 300:
            return Response({"error": {"code": "INVALID_SSO_REQUEST", "message": "Invalid or expired SSO request.", "details": {}}}, status=401)
        payload = f"{external_id}|{email}|{timestamp}"
        expected = hmac.new(settings.MOODLE_SSO_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not settings.MOODLE_SSO_SECRET or not hmac.compare_digest(expected, signature):
            return Response({"error": {"code": "INVALID_SSO_SIGNATURE", "message": "Invalid SSO signature.", "details": {}}}, status=401)
        mapping = ExternalUserMapping.objects.select_related("user").filter(
            provider=ExternalUserMapping.Provider.MOODLE, external_user_id=external_id,
        ).first()
        user = mapping.user if mapping else User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email, username=f"moodle-{external_id}",
                first_name=request.data.get("first_name", ""),
                last_name=request.data.get("last_name", ""),
            )
        ExternalUserMapping.objects.update_or_create(
            provider=ExternalUserMapping.Provider.MOODLE, external_user_id=external_id,
            defaults={"user": user, "metadata": {"email": email}},
        )
        student_group, _ = Group.objects.get_or_create(name=GroupName.STUDENT)
        user.groups.add(student_group)
        tokens = token_pair_for_user(user, "moodle")
        return Response({**tokens, "user": UserSerializer(user).data})


class ManagedUserViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ManagedUserSerializer
    permission_classes = [IsAuthenticated, CanManageUsers]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        queryset = User.objects.prefetch_related(
            "groups", "user_permissions", "auth0_identities"
        ).order_by("email")
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(email__icontains=query)
                | Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
            )
        return queryset


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RoleSerializer

    def get_queryset(self):
        return Group.objects.annotate(user_count=Count("user")).prefetch_related(
            "permissions__content_type"
        ).order_by("name")

    def get_permissions(self):
        permission_classes = (
            [IsAuthenticated, CanManagePermissions]
            if self.action == "set_permissions"
            else [IsAuthenticated, CanManageUsers]
        )
        return [permission() for permission in permission_classes]

    @action(detail=True, methods=["patch", "put"], url_path="permissions")
    def set_permissions(self, request, pk=None):
        role = self.get_object()
        serializer = RolePermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role.permissions.set(serializer.context["resolved_permissions"])
        role = self.get_queryset().get(pk=role.pk)
        return Response(self.get_serializer(role).data)


class PermissionCatalogView(APIView):
    permission_classes = [IsAuthenticated, CanManagePermissions]

    def get(self, request):
        permissions = active_permission_queryset().select_related("content_type").order_by(
            "content_type__app_label", "codename"
        )
        return Response(PermissionSerializer(permissions, many=True).data)


class StaffSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from curriculum.models import Program
        from curriculum.selectors import accessible_courses
        from progress.models import CourseProgress
        from students.selectors import visible_enrollments, visible_students

        records = []
        if request.user.has_perm("curriculum.view_program"):
            records.append(
                {
                    "key": "programs",
                    "label": "Programs",
                    "count": Program.objects.count(),
                    "href": "/manage/programs",
                }
            )
        if request.user.has_perm("curriculum.view_course"):
            records.append(
                {
                    "key": "courses",
                    "label": "Courses",
                    "count": accessible_courses(request.user).count(),
                    "href": "/courses",
                }
            )
        if request.user.has_perm("accounts.view_user"):
            records.append(
                {
                    "key": "students",
                    "label": "Students",
                    "count": visible_students(request.user).count(),
                    "href": "/manage/students",
                }
            )
        if request.user.has_perm("students.view_enrollment"):
            records.append(
                {
                    "key": "enrollments",
                    "label": "Enrollments",
                    "count": visible_enrollments(request.user).count(),
                    "href": "/manage/enrollments",
                }
            )
        if request.user.has_perm("progress.view_all_student_progress"):
            progress_count = CourseProgress.objects.count()
        elif request.user.has_perm("progress.view_assigned_student_progress"):
            progress_count = CourseProgress.objects.filter(
                enrollment__student__student_group_memberships__student_group__teacher=request.user
            ).distinct().count()
        else:
            progress_count = None
        if progress_count is not None:
            records.append(
                {
                    "key": "course-progress",
                    "label": "Progress records",
                    "count": progress_count,
                    "href": "/manage/activity-progress-records",
                }
            )
        return Response({"records": records})
