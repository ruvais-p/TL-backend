from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from curriculum.models import Chapter
from students.models import Enrollment

from .models import ActivityProgress, ChapterProgress, CourseProgress, SubtopicProgress
from .serializers import (
    ActivityProgressSerializer, ChapterProgressSerializer,
    CourseProgressSerializer, SubtopicProgressSerializer,
)


def active_enrollments(user):
    return Enrollment.objects.filter(
        student=user, status=Enrollment.Status.ACTIVE,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))


class MyProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = CourseProgress.objects.filter(enrollment__in=active_enrollments(request.user)).select_related("enrollment__course", "enrollment__course_version")
        return Response(CourseProgressSerializer(rows, many=True).data)


class MyActivityProgressListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = ActivityProgress.objects.filter(
            enrollment__in=active_enrollments(request.user),
        ).select_related("activity", "enrollment__course")
        if course_id := request.query_params.get("course"):
            rows = rows.filter(enrollment__course_id=course_id)
        return Response(ActivityProgressSerializer(rows.order_by("-last_accessed_at"), many=True).data)


class MyCourseProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):
        row = CourseProgress.objects.filter(enrollment__in=active_enrollments(request.user), enrollment__course_id=course_id).first()
        if row is None:
            return Response({"detail": "Course progress not found."}, status=404)
        return Response(CourseProgressSerializer(row).data)


class MyChapterProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, chapter_id):
        row = ChapterProgress.objects.filter(
            enrollment__in=active_enrollments(request.user), chapter_id=chapter_id,
        ).first()
        if row is None:
            return Response({"detail": "Chapter progress not found."}, status=404)
        return Response(ChapterProgressSerializer(row).data)


class MyActivityProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, activity_id):
        row = ActivityProgress.objects.filter(
            enrollment__in=active_enrollments(request.user), activity_id=activity_id,
        ).first()
        if row is None:
            return Response({"detail": "Activity progress not found."}, status=404)
        return Response(ActivityProgressSerializer(row).data)
