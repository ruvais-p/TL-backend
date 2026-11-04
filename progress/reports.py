"""Staff reporting: a read-only overview of learner progress scoped to what the viewer can see."""

from datetime import timedelta

from django.db.models import Avg, Count, Max, Q, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsStaffPortalUser
from assessments.models import AssessmentAttempt
from progress.models import ActivityProgress, CourseProgress
from students.models import Enrollment
from students.selectors import visible_enrollments

ACTIVITY_WEEKS = 8
INACTIVE_AFTER_DAYS = 14
ATTENTION_LIMIT = 10


def _round(value, places=1):
    return round(float(value), places) if value is not None else None


def _display_name(user):
    return f"{user.first_name} {user.last_name}".strip() or user.email


class ReportsOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsStaffPortalUser]

    def get(self, request):
        if not request.user.has_perm("students.view_enrollment"):
            raise PermissionDenied("You do not have permission to view reports.")

        now = timezone.now()
        # Re-base on ids so the teacher scoping join cannot duplicate rows in aggregates.
        visible_ids = visible_enrollments(request.user).filter(status=Enrollment.Status.ACTIVE).values("id")
        enrollments = Enrollment.objects.filter(id__in=visible_ids).select_related("student", "course")
        enrollment_ids = list(enrollments.values_list("id", flat=True))
        progress = CourseProgress.objects.filter(enrollment_id__in=enrollment_ids)
        attempts = AssessmentAttempt.objects.filter(
            submitted_at__isnull=False,
            student_id__in=enrollments.values("student_id"),
            learning_check__chapter__course_version__course_id__in=enrollments.values("course_id"),
        )

        by_status = dict(progress.values_list("status").annotate(total=Count("id")))
        completed = by_status.get("COMPLETED", 0)
        attempt_totals = attempts.aggregate(total=Count("id"), passed=Count("id", filter=Q(passed=True)), average=Avg("percentage"))
        time_total = ActivityProgress.objects.filter(enrollment_id__in=enrollment_ids).aggregate(total=Sum("time_spent_seconds"))["total"] or 0
        learner_count = enrollments.values("student_id").distinct().count()
        totals = {
            "learners": learner_count,
            "active_enrollments": len(enrollment_ids),
            "completed_enrollments": completed,
            "completion_rate": _round(completed * 100 / len(enrollment_ids)) if enrollment_ids else 0,
            "average_progress": _round(progress.aggregate(value=Avg("progress_percentage"))["value"]) or 0,
            "check_attempts": attempt_totals["total"],
            "check_pass_rate": _round(attempt_totals["passed"] * 100 / attempt_totals["total"]) if attempt_totals["total"] else None,
            "average_check_score": _round(attempt_totals["average"]),
            "learning_hours": _round(time_total / 3600),
        }

        courses = []
        course_rows = (
            enrollments.values("course_id", "course__name", "course__code")
            .annotate(
                enrolled=Count("id"),
                completed=Count("id", filter=Q(course_progress__status="COMPLETED")),
                in_progress=Count("id", filter=Q(course_progress__status="IN_PROGRESS")),
                average_progress=Avg("course_progress__progress_percentage"),
            )
            .order_by("course__name")
        )
        attempts_by_course = {
            row["learning_check__chapter__course_version__course_id"]: row
            for row in attempts.values("learning_check__chapter__course_version__course_id").annotate(
                total=Count("id"), passed=Count("id", filter=Q(passed=True)), average=Avg("percentage")
            )
        }
        for row in course_rows:
            checks = attempts_by_course.get(row["course_id"], {})
            courses.append({
                "id": str(row["course_id"]),
                "name": row["course__name"],
                "code": row["course__code"],
                "enrolled": row["enrolled"],
                "completed": row["completed"],
                "in_progress": row["in_progress"],
                "not_started": row["enrolled"] - row["completed"] - row["in_progress"],
                "average_progress": _round(row["average_progress"]) or 0,
                "check_attempts": checks.get("total", 0),
                "check_pass_rate": _round(checks["passed"] * 100 / checks["total"]) if checks.get("total") else None,
                "average_check_score": _round(checks.get("average")),
            })

        since = now - timedelta(weeks=ACTIVITY_WEEKS)
        weekly = {
            row["week"].date(): row
            for row in ActivityProgress.objects.filter(enrollment_id__in=enrollment_ids, last_accessed_at__gte=since)
            .annotate(week=TruncWeek("last_accessed_at"))
            .values("week")
            .annotate(learners=Count("enrollment__student_id", distinct=True), activities=Count("id"))
        }
        start = (now - timedelta(days=now.weekday())).date()
        activity = []
        for offset in range(ACTIVITY_WEEKS - 1, -1, -1):
            week = start - timedelta(weeks=offset)
            row = weekly.get(week, {})
            activity.append({"week": week.isoformat(), "learners": row.get("learners", 0), "activities": row.get("activities", 0)})

        cutoff = now - timedelta(days=INACTIVE_AFTER_DAYS)
        attention = []
        candidates = (
            enrollments.exclude(course_progress__status="COMPLETED")
            .annotate(last_seen=Max("activity_progress__last_accessed_at"), progress_value=Max("course_progress__progress_percentage"))
            .filter(Q(last_seen__isnull=True) | Q(last_seen__lt=cutoff))
            .order_by("last_seen", "enrolled_at")[:ATTENTION_LIMIT]
        )
        for enrollment in candidates:
            attention.append({
                "enrollment_id": str(enrollment.id),
                "student_id": str(enrollment.student_id),
                "student": _display_name(enrollment.student),
                "email": enrollment.student.email,
                "course": enrollment.course.name,
                "progress": _round(enrollment.progress_value) or 0,
                "last_seen": enrollment.last_seen,
                "enrolled_at": enrollment.enrolled_at,
            })

        return Response({
            "generated_at": now,
            "inactive_after_days": INACTIVE_AFTER_DAYS,
            "totals": totals,
            "courses": courses,
            "activity": activity,
            "attention": attention,
        })
