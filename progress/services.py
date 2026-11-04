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

    STATUSES = {"NOT_STARTED", "IN_PROGRESS", "COMPLETED"}
    # Upper bound for one write's time delta, so a stale tab cannot inflate totals.
    MAX_TIME_DELTA_SECONDS = 4 * 60 * 60

    @classmethod
    def normalize_status(cls, status):
        if status is None or status == "":
            return None
        value = str(status).strip().upper()
        if value not in cls.STATUSES:
            raise ValidationError("status must be one of not_started, in_progress or completed.")
        return value

    @staticmethod
    def is_completed(progress):
        return str(progress.status).upper() == "COMPLETED" or progress.progress_percentage >= 100

    @classmethod
    @transaction.atomic
    def record_activity_progress(cls, *, student, activity, progress_percentage, time_spent_seconds=0,
                                 status=None, metadata=None, enrollment=None):
        """Record activity progress for a learner and roll it up.

        Completion is monotonic: a lower percentage or a fresh start never
        un-completes an activity. ``time_spent_seconds`` is a delta that is
        added to the stored total.
        """
        # Always hold the enrollment row lock: it serializes concurrent writes
        # for the same learner so rollup counts never read stale siblings.
        if enrollment is None:
            enrollment = cls._enrollment(student, activity)
        else:
            enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
        status = cls.normalize_status(status)
        percentage = cls._percent(progress_percentage)
        now = timezone.now()
        progress, created = ActivityProgress.objects.select_for_update().get_or_create(
            enrollment=enrollment, activity=activity,
        )
        was_completed = not created and cls.is_completed(progress)
        progress.progress_percentage = max(Decimal(str(progress.progress_percentage or 0)), percentage)
        delta = min(max(0, int(time_spent_seconds or 0)), cls.MAX_TIME_DELTA_SECONDS)
        progress.time_spent_seconds = (progress.time_spent_seconds or 0) + delta
        progress.last_accessed_at = now
        progress.started_at = progress.started_at or now
        progress.metadata = metadata if metadata is not None else progress.metadata
        if was_completed or status == "COMPLETED" or progress.progress_percentage >= 100:
            progress.status = "COMPLETED"
            progress.progress_percentage = Decimal("100.00")
            progress.completed_at = progress.completed_at or now
        else:
            progress.status = "IN_PROGRESS"
            progress.completed_at = None
        progress.save()
        # Only completion changes affect the rollups.
        if created or was_completed != cls.is_completed(progress):
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
