from django.db import models, transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.generics import get_object_or_404
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.decorators import action

from accounts.constants import GroupName
from accounts.permissions import HasModelPermission
from curriculum.models import LearningActivity
from .models import (
    ActivityProgress,
    AssessmentAttempt,
    BadgeAward,
    CareerOpportunity,
    OpportunityApplication,
    OpportunityApplicationDocument,
    PointEvent,
)
from students.models import Enrollment
from .serializers import (
    ActivityProgressSerializer,
    BadgeAwardSerializer,
    CareerOpportunitySerializer,
    PointEventSerializer,
    ProgressUpsertSerializer,
    StaffActivityProgressSerializer,
    StaffBadgeAwardSerializer,
    StaffCareerOpportunitySerializer,
    LearnerApplicationCreateSerializer,
    LearnerApplicationSerializer,
    StaffOpportunityApplicationSerializer,
    ApplicationTransitionSerializer,
    ApplicationReviewNoteSerializer,
    StaffLegacyAssessmentAttemptSerializer,
    StaffPointEventSerializer,
)
from .services import ProgressService
from .opportunity_services import OpportunityLifecycleService, OpportunityStateError
from .opportunity_selectors import (
    learner_catalog_opportunities,
    learner_detail_opportunities,
)
from .eligibility import LearnerFactSnapshot
from .application_services import (
    ApplicationSubmissionError,
    ApplicationTransitionError,
    OpportunityApplicationService,
)
from .private_documents import open_resume

EVENT_BADGES = {
    PointEvent.Reason.REACH_PEAK: BadgeAward.Code.FIRST_PEAK,
    PointEvent.Reason.EXPLORE_SLOPES: BadgeAward.Code.SLOPE_READER,
    PointEvent.Reason.EXPORT_REPORT: BadgeAward.Code.BUSINESS_OPTIMISER,
}


def _ensure_enrollment(user, activity):
    course = activity.subtopic.chapter.course_version.course
    enrollment = Enrollment.objects.filter(
        student=user, course=course,
        course_version=activity.subtopic.chapter.course_version,
        status=Enrollment.Status.ACTIVE,
    ).filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
    ).first()
    if enrollment is None:
        raise PermissionDenied("An active enrollment for this course version is required.")
    return enrollment


def _award_event(user, activity, event_code):
    if not event_code:
        return None, None
    try:
        reason = PointEvent.Reason(event_code)
    except ValueError:
        return None, None
    points, _ = PointEvent.objects.get_or_create(
        user=user,
        activity=activity,
        reason=reason,
        defaults={"points": PointEvent.POINTS[reason]},
    )
    badge = None
    badge_code = EVENT_BADGES.get(reason)
    if badge_code:
        badge, _ = BadgeAward.objects.get_or_create(
            user=user, activity=activity, code=badge_code
        )
    if reason == PointEvent.Reason.REACH_PEAK:
        BadgeAward.objects.get_or_create(
            user=user, activity=activity, code=BadgeAward.Code.BUSINESS_OPTIMISER
        )
    return points, badge


class ProgressUpsertView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProgressUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        activity = LearningActivity.objects.filter(id=data["activity"]).first()
        if not activity:
            return Response({"detail": "Activity not found."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            enrollment = _ensure_enrollment(request.user, activity)
            progress = ProgressService.record_activity_progress(
                student=request.user, activity=activity,
                progress_percentage=data.get("progress_percentage", 100 if data.get("status") == "completed" else 0),
                time_spent_seconds=data.get("time_spent_seconds", 0),
                status="COMPLETED" if data.get("status") == "completed" else None,
                enrollment=enrollment,
            )
            extra = progress.extra or {}
            incoming = data.get("extra") or {}
            extra.update(incoming)
            progress.extra = extra
            progress.status = data.get("status") or progress.status
            if progress.status == "completed" and not progress.completed_at:
                progress.completed_at = timezone.now()
            progress.save()
            awarded_points, awarded_badge = _award_event(
                request.user, activity, data.get("event")
            )

        payload = ActivityProgressSerializer(progress).data
        payload["points"] = PointEventSerializer(awarded_points).data if awarded_points else None
        payload["badge"] = BadgeAwardSerializer(awarded_badge).data if awarded_badge else None
        return Response(payload)


class ActivityProgressActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, activity_id, action):
        activity = LearningActivity.objects.filter(id=activity_id).select_related("subtopic__chapter__course_version__course").first()
        if activity is None:
            return Response({"detail": "Activity not found."}, status=404)
        action_payload = request.data.copy()
        action_payload["activity"] = str(activity_id)
        serializer = ProgressUpsertSerializer(data=action_payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if action == "start":
            data["progress_percentage"] = max(0, data.get("progress_percentage", 0))
            data["status"] = "IN_PROGRESS"
        elif action == "complete":
            data["progress_percentage"] = 100
            data["status"] = "COMPLETED"
        else:
            data["status"] = data.get("status")
        progress = ProgressService.record_activity_progress(
            student=request.user, activity=activity,
            progress_percentage=data.get("progress_percentage", 0),
            time_spent_seconds=data.get("time_spent_seconds", 0),
            status=data.get("status"), metadata=data.get("metadata"),
        )
        return Response(ActivityProgressSerializer(progress).data)


class GamificationMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        points = PointEvent.objects.filter(user=request.user)
        badges = BadgeAward.objects.filter(user=request.user)
        total = sum(p.points for p in points)
        return Response(
            {
                "total_points": total,
                "events": PointEventSerializer(points, many=True).data,
                "badges": BadgeAwardSerializer(badges, many=True).data,
            }
        )


class CareerOpportunityListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        snapshot = LearnerFactSnapshot.for_user(request.user)
        qs = learner_catalog_opportunities(
            request.user,
            search=request.query_params.get("search", "").strip(),
            employment_type=request.query_params.get("employment_type", ""),
            workplace_mode=request.query_params.get("workplace_mode", ""),
        )
        return Response(
            CareerOpportunitySerializer(
                qs,
                many=True,
                context={"request": request, "eligibility_snapshot": snapshot},
            ).data
        )


class CareerOpportunityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, opportunity_id):
        snapshot = LearnerFactSnapshot.for_user(request.user)
        opportunity = get_object_or_404(
            learner_detail_opportunities(request.user), id=opportunity_id
        )
        return Response(
            CareerOpportunitySerializer(
                opportunity,
                context={"request": request, "eligibility_snapshot": snapshot},
            ).data
        )


class CareerOpportunityApplicationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, opportunity_id):
        opportunity = get_object_or_404(CareerOpportunity, id=opportunity_id)
        serializer = LearnerApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = OpportunityApplicationService.submit(
                opportunity=opportunity,
                applicant=request.user,
                **serializer.validated_data,
            )
        except ApplicationSubmissionError as exc:
            response_status = {
                "duplicate_application": status.HTTP_409_CONFLICT,
                "not_available": status.HTTP_404_NOT_FOUND,
                "not_open": status.HTTP_409_CONFLICT,
            }.get(exc.code, status.HTTP_400_BAD_REQUEST)
            payload = {"detail": str(exc), "code": exc.code}
            if exc.reasons:
                payload["reasons"] = list(exc.reasons)
            return Response(payload, status=response_status)
        return Response(
            LearnerApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )


class LearnerApplicationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        applications = OpportunityApplication.objects.filter(
            applicant=request.user
        ).select_related("opportunity", "resume_document")
        return Response(LearnerApplicationSerializer(applications, many=True).data)


class LearnerApplicationWithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, application_id):
        application = get_object_or_404(
            OpportunityApplication, id=application_id, applicant=request.user
        )
        try:
            application = OpportunityApplicationService.withdraw_by_applicant(
                application=application, actor=request.user
            )
        except ApplicationTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(LearnerApplicationSerializer(application).data)


class LearnerApplicationResumeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, application_id):
        application = get_object_or_404(
            OpportunityApplication.objects.select_related("resume_document"),
            id=application_id,
            applicant=request.user,
        )
        document = get_object_or_404(
            OpportunityApplicationDocument, application=application
        )
        stream = open_resume(document=document, user=request.user)
        return FileResponse(
            stream,
            as_attachment=True,
            filename=document.original_filename,
            content_type=document.mime_type,
        )


def visible_staff_activity_progress(user):
    queryset = ActivityProgress.objects.select_related(
        "enrollment__student", "enrollment__course", "activity"
    )
    if user.has_perm("progress.view_all_student_progress"):
        return queryset
    if user.has_perm("progress.view_assigned_student_progress"):
        return queryset.filter(
            enrollment__student__student_group_memberships__student_group__teacher=user
        ).distinct()
    if user.groups.filter(name=GroupName.STUDENT).exists():
        return queryset.filter(enrollment__student=user)
    return queryset.none()


class ActivityProgressStaffViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActivityProgress.objects.all()
    serializer_class = StaffActivityProgressSerializer
    permission_classes = [IsAuthenticated, HasModelPermission]

    def get_queryset(self):
        return visible_staff_activity_progress(self.request.user).order_by(
            "-updated_at"
        )


class PointEventStaffViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PointEvent.objects.select_related("user", "activity")
    serializer_class = StaffPointEventSerializer
    permission_classes = [IsAuthenticated, HasModelPermission]


class BadgeAwardStaffViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BadgeAward.objects.select_related("user", "activity")
    serializer_class = StaffBadgeAwardSerializer
    permission_classes = [IsAuthenticated, HasModelPermission]


class CareerOpportunityStaffViewSet(viewsets.ModelViewSet):
    queryset = CareerOpportunity.objects.select_related("company_logo").prefetch_related(
        "audience_groups"
    )
    serializer_class = StaffCareerOpportunitySerializer
    permission_classes = [IsAuthenticated, HasModelPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                models.Q(title__icontains=search)
                | models.Q(company_name__icontains=search)
                | models.Q(summary__icontains=search)
            )
        for query_name, field_name in (
            ("employment_type", "employment_type"),
            ("workplace_mode", "workplace_mode"),
            ("lifecycle_status", "lifecycle_status"),
        ):
            value = self.request.query_params.get(query_name)
            if value:
                queryset = queryset.filter(**{field_name: value})
        return queryset

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action in {"publish", "close", "archive"}:
            # Lifecycle POSTs mutate an existing record and require change permission.
            permissions[-1].has_permission = lambda request, view: request.user.has_perm(
                "progress.change_careeropportunity"
            )
        return permissions

    def _lifecycle_response(self, operation):
        try:
            opportunity = operation(self.get_object())
        except OpportunityStateError as exc:
            return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            payload = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(opportunity).data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return self._lifecycle_response(OpportunityLifecycleService.publish)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._lifecycle_response(OpportunityLifecycleService.close)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return self._lifecycle_response(OpportunityLifecycleService.archive)


class ApplicationReviewPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if view.action == "resume":
            return request.user.has_perm(
                "progress.review_opportunityapplication"
            ) and request.user.has_perm(
                "progress.download_opportunityapplicationdocument"
            )
        if view.action in {"transition", "review_note"}:
            return request.user.has_perm(
                "progress.change_opportunityapplication"
            ) and request.user.has_perm("progress.review_opportunityapplication")
        return request.user.has_perm("progress.view_opportunityapplication")


class OpportunityApplicationStaffViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OpportunityApplication.objects.select_related(
        "opportunity", "applicant", "reviewed_by", "resume_document"
    )
    serializer_class = StaffOpportunityApplicationSerializer
    permission_classes = [IsAuthenticated, ApplicationReviewPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        opportunity = self.request.query_params.get("opportunity")
        application_status = self.request.query_params.get("status")
        search = self.request.query_params.get("search", "").strip()
        if opportunity:
            queryset = queryset.filter(opportunity_id=opportunity)
        if application_status:
            queryset = queryset.filter(status=application_status)
        if search:
            queryset = queryset.filter(
                models.Q(applicant_name__icontains=search)
                | models.Q(applicant_email__icontains=search)
                | models.Q(contact_phone__icontains=search)
            )
        return queryset

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        serializer = ApplicationTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = OpportunityApplicationService.transition_by_staff(
                application=self.get_object(),
                actor=request.user,
                new_status=serializer.validated_data["status"],
                review_notes=serializer.validated_data.get("review_notes"),
            )
        except ApplicationTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(application).data)

    @action(detail=True, methods=["patch"])
    def review_note(self, request, pk=None):
        serializer = ApplicationReviewNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = OpportunityApplicationService.update_review_notes(
            application=self.get_object(),
            actor=request.user,
            review_notes=serializer.validated_data["review_notes"],
        )
        return Response(self.get_serializer(application).data)

    @action(detail=True, methods=["get"])
    def resume(self, request, pk=None):
        application = self.get_object()
        document = get_object_or_404(
            OpportunityApplicationDocument, application=application
        )
        stream = open_resume(document=document, user=request.user)
        return FileResponse(
            stream,
            as_attachment=True,
            filename=document.original_filename,
            content_type=document.mime_type,
        )


class LegacyAssessmentAttemptStaffViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AssessmentAttempt.objects.select_related("user", "activity")
    serializer_class = StaffLegacyAssessmentAttemptSerializer
    permission_classes = [IsAuthenticated, HasModelPermission]
