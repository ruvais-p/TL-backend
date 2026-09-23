from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from accounts.constants import GroupName
from students.models import Enrollment
from .permissions import AssessmentPermission

from .models import (
    AssessmentAnswer, AssessmentAttempt, CaseStudy, CaseStudyQuestion,
    LearningCheck, LearningCheckQuestion, Question, QuestionOption,
)
from .serializers import (
    AssessmentAttemptSerializer, CaseStudyQuestionSerializer, CaseStudySerializer,
    LearningCheckQuestionSerializer, LearningCheckSerializer, QuestionOptionSerializer,
    QuestionSerializer, StaffAssessmentAnswerSerializer,
    StaffAssessmentAttemptSerializer, StudentLearningCheckSerializer,
    SubmitAttemptSerializer,
)
from .services import AssessmentService


class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.prefetch_related("options").all()
    serializer_class = QuestionSerializer
    permission_classes = [AssessmentPermission]


class QuestionOptionViewSet(viewsets.ModelViewSet):
    queryset = QuestionOption.objects.all()
    serializer_class = QuestionOptionSerializer
    permission_classes = [AssessmentPermission]


class CaseStudyViewSet(viewsets.ModelViewSet):
    queryset = CaseStudy.objects.prefetch_related("questions__question").all()
    serializer_class = CaseStudySerializer
    permission_classes = [AssessmentPermission]


class CaseStudyQuestionViewSet(viewsets.ModelViewSet):
    queryset = CaseStudyQuestion.objects.all()
    serializer_class = CaseStudyQuestionSerializer
    permission_classes = [AssessmentPermission]


class LearningCheckViewSet(viewsets.ModelViewSet):
    queryset = LearningCheck.objects.prefetch_related("questions__question__options").all()
    serializer_class = LearningCheckSerializer
    permission_classes = [AssessmentPermission]

    def get_serializer_class(self):
        request_user = getattr(self.request, "user", None)
        if (
            request_user
            and request_user.groups.filter(name=GroupName.STUDENT).exists()
            and not request_user.is_superuser
        ):
            return StudentLearningCheckSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        queryset = super().get_queryset()
        if request_user := getattr(self.request, "user", None):
            if request_user.groups.filter(name=GroupName.STUDENT).exists() and not request_user.is_superuser:
                queryset = queryset.filter(status="PUBLISHED").filter(
                    Q(chapter__course_version__course__student_enrollments__student=request_user,
                      chapter__course_version__course__student_enrollments__status=Enrollment.Status.ACTIVE,
                      chapter__course_version__course__student_enrollments__expires_at__isnull=True)
                    | Q(chapter__course_version__course__student_enrollments__student=request_user,
                       chapter__course_version__course__student_enrollments__status=Enrollment.Status.ACTIVE,
                       chapter__course_version__course__student_enrollments__expires_at__gt=timezone.now())
                ).distinct()
        return queryset

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        attempt = AssessmentService.start_attempt(student=request.user, learning_check=self.get_object())
        return Response(AssessmentAttemptSerializer(attempt).data, status=201)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        serializer = SubmitAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt_id = serializer.validated_data.get("attempt_id") or request.data.get("attempt_id")
        if not attempt_id:
            return Response({"detail": "attempt_id is required."}, status=400)
        from .models import AssessmentAttempt
        attempt = AssessmentAttempt.objects.filter(pk=attempt_id, learning_check=self.get_object()).first()
        if attempt is None:
            return Response({"detail": "Attempt not found."}, status=404)
        attempt = AssessmentService.submit_attempt(student=request.user, attempt=attempt, answers=serializer.validated_data["answers"], time_spent_seconds=serializer.validated_data["time_spent_seconds"])
        return Response(AssessmentAttemptSerializer(attempt).data)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        from .models import AssessmentAttempt
        attempts = AssessmentAttempt.objects.filter(student=request.user, learning_check=self.get_object()).order_by("attempt_number")
        return Response(AssessmentAttemptSerializer(attempts, many=True).data)


class LearningCheckQuestionViewSet(viewsets.ModelViewSet):
    queryset = LearningCheckQuestion.objects.select_related("learning_check", "question").all()
    serializer_class = LearningCheckQuestionSerializer
    permission_classes = [AssessmentPermission]


def visible_staff_attempts(user):
    queryset = AssessmentAttempt.objects.select_related(
        "student", "learning_check__chapter__course_version__course"
    )
    if user.has_perm("progress.view_all_student_progress"):
        return queryset
    if user.has_perm("progress.view_assigned_student_progress"):
        return queryset.filter(
            student__student_group_memberships__student_group__teacher=user
        ).distinct()
    if user.groups.filter(name=GroupName.STUDENT).exists():
        return queryset.filter(student=user)
    return queryset.none()


class AssessmentAttemptStaffViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AssessmentAttempt.objects.all()
    serializer_class = StaffAssessmentAttemptSerializer
    permission_classes = [AssessmentPermission]

    def get_queryset(self):
        return visible_staff_attempts(self.request.user).order_by("-started_at")


class AssessmentAnswerStaffViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AssessmentAnswer.objects.all()
    serializer_class = StaffAssessmentAnswerSerializer
    permission_classes = [AssessmentPermission]

    def get_queryset(self):
        return AssessmentAnswer.objects.filter(
            attempt__in=visible_staff_attempts(self.request.user)
        ).select_related("attempt__student", "question").order_by("-answered_at")
