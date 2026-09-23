from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.serializers import UserSerializer
from assessments.models import AssessmentAttempt
from progress.models import ActivityProgress, BadgeAward, ChapterProgress, CourseProgress, PointEvent, SubtopicProgress

from .permissions import CanAccessStudentDomain
from .selectors import (
    visible_assignments, visible_enrollments, visible_external_mappings,
    visible_memberships, visible_student_groups, visible_students,
)
from .serializers import (
    CourseAssignmentSerializer, EnrollmentSerializer, ExternalUserMappingSerializer,
    StudentGroupMemberSerializer, StudentGroupSerializer,
)
from .services import (
    add_student_to_group, create_course_assignment, create_enrollment,
    create_student_group, upsert_external_mapping,
)

User = get_user_model()


class StudentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, CanAccessStudentDomain]

    def get_queryset(self):
        return visible_students(self.request.user)

    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None):
        student = self.get_object()
        memberships = student.student_group_memberships.select_related("student_group", "student_group__teacher")
        group_ids = list(memberships.values_list("student_group_id", flat=True))
        enrollments = list(
            visible_enrollments(request.user).filter(student=student)
            .select_related("course__program", "course_version")
            .prefetch_related("course_version__chapters__subtopics__activities")
        )
        enrollment_ids = [enrollment.id for enrollment in enrollments]
        course_progress = {row.enrollment_id: row for row in CourseProgress.objects.filter(enrollment_id__in=enrollment_ids)}
        chapter_progress = {(row.enrollment_id, row.chapter_id): row for row in ChapterProgress.objects.filter(enrollment_id__in=enrollment_ids)}
        subtopic_progress = {(row.enrollment_id, row.subtopic_id): row for row in SubtopicProgress.objects.filter(enrollment_id__in=enrollment_ids)}
        activity_progress = {(row.enrollment_id, row.activity_id): row for row in ActivityProgress.objects.filter(enrollment_id__in=enrollment_ids)}
        attempts = AssessmentAttempt.objects.filter(student=student).select_related("learning_check__chapter")
        attempts_by_chapter = {}
        for attempt in attempts:
            attempts_by_chapter.setdefault(attempt.learning_check.chapter_id, []).append({
                "id": str(attempt.id), "title": attempt.learning_check.title,
                "attempt_number": attempt.attempt_number, "status": attempt.status,
                "score": attempt.score, "max_score": attempt.max_score, "percentage": attempt.percentage,
                "passed": attempt.passed, "time_spent_seconds": attempt.time_spent_seconds,
                "started_at": attempt.started_at, "submitted_at": attempt.submitted_at,
            })

        course_rows = []
        for enrollment in enrollments:
            course_row = course_progress.get(enrollment.id)
            chapters = []
            for chapter in enrollment.course_version.chapters.all():
                chapter_row = chapter_progress.get((enrollment.id, chapter.id))
                subtopics = []
                for subtopic in chapter.subtopics.all():
                    subtopic_row = subtopic_progress.get((enrollment.id, subtopic.id))
                    activities = []
                    for activity in subtopic.activities.all():
                        activity_row = activity_progress.get((enrollment.id, activity.id))
                        activities.append({
                            "id": str(activity.id), "title": activity.title, "activity_type": activity.activity_type,
                            "is_required": activity.is_required, "estimated_minutes": activity.estimated_minutes,
                            "status": activity_row.status if activity_row else "NOT_STARTED",
                            "progress_percentage": activity_row.progress_percentage if activity_row else 0,
                            "time_spent_seconds": activity_row.time_spent_seconds if activity_row else 0,
                            "attempt_count": activity_row.attempt_count if activity_row else 0,
                            "started_at": activity_row.started_at if activity_row else None,
                            "last_accessed_at": activity_row.last_accessed_at if activity_row else None,
                            "completed_at": activity_row.completed_at if activity_row else None,
                        })
                    subtopics.append({
                        "id": str(subtopic.id), "title": subtopic.title,
                        "status": subtopic_row.status if subtopic_row else "NOT_STARTED",
                        "progress_percentage": subtopic_row.progress_percentage if subtopic_row else 0,
                        "completed_activities": subtopic_row.completed_activities if subtopic_row else 0,
                        "total_required_activities": subtopic_row.total_required_activities if subtopic_row else subtopic.activities.filter(is_required=True).count(),
                        "activities": activities,
                    })
                chapters.append({
                    "id": str(chapter.id), "title": chapter.title, "chapter_number": chapter.chapter_number,
                    "status": chapter_row.status if chapter_row else "NOT_STARTED",
                    "progress_percentage": chapter_row.progress_percentage if chapter_row else 0,
                    "completed_subtopics": chapter_row.completed_subtopics if chapter_row else 0,
                    "total_subtopics": chapter_row.total_subtopics if chapter_row else chapter.subtopics.filter(is_required=True).count(),
                    "learning_check_score": chapter_row.learning_check_score if chapter_row else None,
                    "assessments": attempts_by_chapter.get(chapter.id, []), "subtopics": subtopics,
                })
            course_rows.append({
                "enrollment_id": str(enrollment.id), "course_id": str(enrollment.course_id),
                "course_name": enrollment.course.name, "program_name": enrollment.course.program.name,
                "version_name": enrollment.course_version.name, "enrollment_status": enrollment.status,
                "enrolled_at": enrollment.enrolled_at, "started_at": enrollment.started_at,
                "completed_at": enrollment.completed_at, "expires_at": enrollment.expires_at,
                "status": course_row.status if course_row else "NOT_STARTED",
                "progress_percentage": course_row.progress_percentage if course_row else 0,
                "completed_chapters": course_row.completed_chapters if course_row else 0,
                "total_chapters": course_row.total_chapters if course_row else enrollment.course_version.chapters.filter(is_required=True).count(),
                "average_score": course_row.average_score if course_row else 0,
                "last_activity_at": course_row.last_activity_at if course_row else None,
                "chapters": chapters,
            })

        assignments = visible_assignments(request.user).filter(
            Q(student=student) | Q(student_group_id__in=group_ids)
        ).select_related("course", "course_version", "student_group", "assigned_by")
        points = PointEvent.objects.filter(user=student)
        badges = BadgeAward.objects.filter(user=student)
        total_time = sum(
            activity["time_spent_seconds"]
            for course in course_rows for chapter in course["chapters"]
            for subtopic in chapter["subtopics"] for activity in subtopic["activities"]
        )
        return Response({
            "student": UserSerializer(student).data,
            "groups": [{
                "id": str(member.student_group_id), "name": member.student_group.name,
                "grade": member.student_group.grade, "academic_year": member.student_group.academic_year,
                "teacher": member.student_group.teacher.display_name if member.student_group.teacher else None,
                "joined_at": member.joined_at,
            } for member in memberships],
            "summary": {
                "assigned_courses": len(course_rows),
                "completed_courses": sum(course["status"] == "COMPLETED" for course in course_rows),
                "average_completion": round(sum(float(course["progress_percentage"]) for course in course_rows) / len(course_rows), 2) if course_rows else 0,
                "average_score": round(sum(float(course["average_score"]) for course in course_rows) / len(course_rows), 2) if course_rows else 0,
                "time_spent_seconds": total_time, "total_points": sum(point.points for point in points),
                "badges_earned": badges.count(), "assessment_attempts": attempts.count(),
            },
            "courses": course_rows,
            "assignments": [{
                "id": str(item.id), "course_name": item.course.name, "version_name": item.course_version.name,
                "source": item.student_group.name if item.student_group else "Individual",
                "assigned_by": item.assigned_by.display_name, "assigned_at": item.assigned_at,
                "due_date": item.due_date, "status": item.status,
            } for item in assignments],
            "badges": [{"code": badge.code, "label": badge.get_code_display(), "earned_at": badge.created_at} for badge in badges],
        })


class TeacherViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, CanAccessStudentDomain]

    def get_queryset(self):
        return User.objects.filter(groups__name="TEACHER", is_active=True).distinct().prefetch_related("groups")


class StudentGroupViewSet(viewsets.ModelViewSet):
    serializer_class = StudentGroupSerializer
    permission_classes = [IsAuthenticated, CanAccessStudentDomain]

    def get_queryset(self):
        return visible_student_groups(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = create_student_group(actor=self.request.user, **serializer.validated_data)

    @action(detail=True, methods=["post"], url_path="members")
    def add_member(self, request, pk=None):
        student = User.objects.get(pk=request.data.get("student"))
        membership = add_student_to_group(actor=request.user, student_group=self.get_object(), student=student)
        return Response(StudentGroupMemberSerializer(membership).data)


class StudentGroupMemberViewSet(viewsets.ModelViewSet):
    serializer_class = StudentGroupMemberSerializer
    permission_classes = [IsAuthenticated, CanAccessStudentDomain]

    def get_queryset(self):
        return visible_memberships(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = add_student_to_group(actor=self.request.user, **serializer.validated_data)


class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated, CanAccessStudentDomain]

    def get_queryset(self):
        return visible_enrollments(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = create_enrollment(actor=self.request.user, **serializer.validated_data)


class CourseAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = CourseAssignmentSerializer
    permission_classes = [IsAuthenticated, CanAccessStudentDomain]

    def get_queryset(self):
        queryset = visible_assignments(self.request.user)
        student_group = self.request.query_params.get("student_group")
        return queryset.filter(student_group_id=student_group) if student_group else queryset

    def perform_create(self, serializer):
        serializer.instance = create_course_assignment(actor=self.request.user, **serializer.validated_data)


class ExternalUserMappingViewSet(viewsets.ModelViewSet):
    serializer_class = ExternalUserMappingSerializer
    permission_classes = [IsAuthenticated, CanAccessStudentDomain]

    def get_queryset(self):
        return visible_external_mappings(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = upsert_external_mapping(actor=self.request.user, **serializer.validated_data)
