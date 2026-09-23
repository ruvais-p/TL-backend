from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from curriculum.models import Chapter, LearningActivity, PublishStatus, Subtopic
from students.models import Enrollment

from .models import ActivityProgress, ChapterProgress, CourseProgress, SubtopicProgress


class ProgressService:
    """Single write path for canonical activity-to-course progress propagation."""

    @staticmethod
    def _enrollment(student, activity):
        version = activity.subtopic.chapter.course_version
        enrollment = Enrollment.objects.select_for_update().filter(
            student=student, course=version.course, course_version=version,
            status=Enrollment.Status.ACTIVE,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).first()
        if enrollment is None:
            raise PermissionDenied("An active enrollment for this course version is required.")
        return enrollment

    @staticmethod
    def _percent(value):
        value = Decimal(str(value))
        if value < 0 or value > 100:
            raise ValidationError("progress_percentage must be between 0 and 100.")
        return value.quantize(Decimal("0.01"))

    @classmethod
    @transaction.atomic
    def record_activity_progress(cls, *, student, activity, progress_percentage, time_spent_seconds=0,
                                 status=None, metadata=None, enrollment=None):
        enrollment = enrollment or cls._enrollment(student, activity)
        percentage = cls._percent(progress_percentage)
        now = timezone.now()
        progress, _ = ActivityProgress.objects.select_for_update().get_or_create(
            enrollment=enrollment, activity=activity,
        )
        progress.progress_percentage = percentage
        progress.time_spent_seconds = max(0, int(time_spent_seconds or 0))
        progress.last_accessed_at = now
        progress.started_at = progress.started_at or now
        progress.metadata = metadata if metadata is not None else progress.metadata
        progress.status = status or ("COMPLETED" if percentage >= 100 else "IN_PROGRESS")
        if progress.status.lower() == "completed" or percentage >= 100:
            progress.status = "COMPLETED"
            progress.completed_at = progress.completed_at or now
        progress.save()
        cls.recalculate_subtopic(enrollment=enrollment, subtopic=activity.subtopic)
        return progress

    @classmethod
    def complete_activity(cls, *, student, activity, enrollment=None):
        return cls.record_activity_progress(
            student=student, activity=activity, progress_percentage=100,
            status="COMPLETED", enrollment=enrollment,
        )

    @classmethod
    @transaction.atomic
    def recalculate_subtopic(cls, *, enrollment, subtopic):
        activities = list(subtopic.activities.filter(is_required=True))
        total = len(activities)
        completed = ActivityProgress.objects.filter(
            enrollment=enrollment, activity__in=activities,
        ).filter(Q(status__iexact="COMPLETED") | Q(progress_percentage__gte=100)).count()
        percentage = Decimal("0") if total == 0 else (Decimal(completed) * 100 / Decimal(total)).quantize(Decimal("0.01"))
        now = timezone.now()
        row, _ = SubtopicProgress.objects.select_for_update().get_or_create(enrollment=enrollment, subtopic=subtopic)
        row.progress_percentage = percentage
        row.percent_complete = percentage
        row.completed_activities = completed
        row.total_required_activities = total
        row.status = "COMPLETED" if total and completed == total else ("IN_PROGRESS" if completed else "NOT_STARTED")
        row.started_at = row.started_at or (now if completed else None)
        row.last_accessed_at = now
        row.completed_at = now if row.status == "COMPLETED" else None
        row.save()
        cls.recalculate_chapter(enrollment=enrollment, chapter=subtopic.chapter)
        return row

    @classmethod
    @transaction.atomic
    def recalculate_chapter(cls, *, enrollment, chapter):
        subtopics = list(chapter.subtopics.filter(is_required=True))
        total = len(subtopics)
        completed = SubtopicProgress.objects.filter(
            enrollment=enrollment, subtopic__in=subtopics, status="COMPLETED",
        ).count()
        percentage = Decimal("0") if total == 0 else (Decimal(completed) * 100 / Decimal(total)).quantize(Decimal("0.01"))
        now = timezone.now()
        row, _ = ChapterProgress.objects.select_for_update().get_or_create(enrollment=enrollment, chapter=chapter)
        row.progress_percentage = percentage
        row.percent_complete = percentage
        row.completed_subtopics = completed
        row.total_subtopics = total
        row.status = "COMPLETED" if total and completed == total else ("IN_PROGRESS" if completed else "NOT_STARTED")
        row.started_at = row.started_at or (now if completed else None)
        row.last_accessed_at = now
        row.completed_at = now if row.status == "COMPLETED" else None
        row.save()
        cls.recalculate_course(enrollment=enrollment)
        return row

    @classmethod
    @transaction.atomic
    def recalculate_course(cls, *, enrollment):
        chapters = list(enrollment.course_version.chapters.filter(is_required=True))
        total = len(chapters)
        completed = ChapterProgress.objects.filter(enrollment=enrollment, chapter__in=chapters, status="COMPLETED").count()
        percentage = Decimal("0") if total == 0 else (Decimal(completed) * 100 / Decimal(total)).quantize(Decimal("0.01"))
        now = timezone.now()
        row, _ = CourseProgress.objects.select_for_update().get_or_create(enrollment=enrollment)
        row.progress_percentage = percentage
        row.percent_complete = percentage
        row.completed_chapters = completed
        row.total_chapters = total
        row.status = "COMPLETED" if total and completed == total else ("IN_PROGRESS" if completed else "NOT_STARTED")
        row.started_at = row.started_at or (now if completed else None)
        row.last_accessed_at = now
        row.last_activity_at = now
        row.completed_at = now if row.status == "COMPLETED" else None
        row.save()
        return row
