import uuid

from django.conf import settings
from django.db import models


class TimestampedUUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublishStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    IN_REVIEW = "IN_REVIEW", "In review"
    APPROVED = "APPROVED", "Approved"
    PUBLISHED = "PUBLISHED", "Published"
    ARCHIVED = "ARCHIVED", "Archived"


class Program(TimestampedUUIDModel):
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    grade = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="programs_created",
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["status", "created_at"], name="program_status_created_idx")]

    def __str__(self) -> str:
        return self.name


class Course(TimestampedUUIDModel):
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="courses")
    name = models.CharField(max_length=200)
    code = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    thumbnail = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="course_thumbnails"
    )
    status = models.CharField(max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT, db_index=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="courses_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="courses_updated",
    )

    class Meta:
        ordering = ["display_order", "name"]
        permissions = [
            ("publish_course", "Can publish courses"),
            ("archive_course", "Can archive courses"),
            ("duplicate_course", "Can duplicate courses"),
            ("assign_course", "Can assign courses"),
        ]
        indexes = [models.Index(fields=["program", "status", "display_order"], name="course_prog_status_ord_idx")]

    def __str__(self) -> str:
        return self.name


class CourseVersion(TimestampedUUIDModel):
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="course_versions_created",
    )

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["course", "version_number"], name="unique_course_version_number")
        ]
        indexes = [models.Index(fields=["course", "status", "version_number"], name="version_course_status_num_idx")]

    def __str__(self) -> str:
        return f"{self.course.name} — {self.name}"


class Chapter(TimestampedUUIDModel):
    course_version = models.ForeignKey(CourseVersion, on_delete=models.PROTECT, related_name="chapters")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    chapter_number = models.PositiveIntegerField()
    estimated_minutes = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT, db_index=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    completion_rule = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["display_order", "chapter_number", "title"]
        constraints = [
            models.UniqueConstraint(fields=["course_version", "slug"], name="unique_chapter_slug_per_version"),
            models.UniqueConstraint(fields=["course_version", "chapter_number"], name="unique_chapter_number_per_version"),
        ]
        permissions = [
            ("publish_chapter", "Can publish chapters"),
            ("duplicate_chapter", "Can duplicate chapters"),
        ]
        indexes = [models.Index(fields=["course_version", "status", "display_order"], name="chapter_ver_status_ord_idx")]

    def __str__(self) -> str:
        return self.title


class Subtopic(TimestampedUUIDModel):
    chapter = models.ForeignKey(Chapter, on_delete=models.PROTECT, related_name="subtopics")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    learning_objectives = models.JSONField(default=list, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=0)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_required = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT, db_index=True)

    class Meta:
        ordering = ["display_order", "title"]
        constraints = [models.UniqueConstraint(fields=["chapter", "slug"], name="unique_subtopic_slug_per_chapter")]
        indexes = [models.Index(fields=["chapter", "status", "display_order"], name="subtopic_ch_status_ord_idx")]

    def __str__(self) -> str:
        return self.title


class LearningActivity(TimestampedUUIDModel):
    class ActivityType(models.TextChoices):
        CONCEPT_VIDEO = "CONCEPT_VIDEO", "Concept video"
        EXPERIMENT = "EXPERIMENT", "Experiment"
        CONCEPT_OVERVIEW = "CONCEPT_OVERVIEW", "Concept overview"
        OBSERVE_LEARN_PRACTICE = "OBSERVE_LEARN_PRACTICE", "Observe, learn, practice"
        HOMEWORK = "HOMEWORK", "Homework"
        INTERACTIVE_WORKSHOP = "INTERACTIVE_WORKSHOP", "Interactive workshop"
        SIMULATION = "SIMULATION", "Simulation"
        READING = "READING", "Reading"
        PDF = "PDF", "PDF"
        INTERACTIVE = "INTERACTIVE", "Interactive"
        ASSIGNMENT = "ASSIGNMENT", "Assignment"
        PROJECT = "PROJECT", "Project"
        LIVE_CLASS = "LIVE_CLASS", "Live class"
        FLASHCARD = "FLASHCARD", "Flashcard"

    subtopic = models.ForeignKey(Subtopic, on_delete=models.PROTECT, related_name="activities")
    activity_type = models.CharField(max_length=40, choices=ActivityType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0, db_index=True)
    is_required = models.BooleanField(default=True)
    estimated_minutes = models.PositiveIntegerField(default=0)
    completion_rule = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=PublishStatus.choices, default=PublishStatus.DRAFT, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activities_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activities_updated",
    )

    class Meta:
        ordering = ["display_order", "title"]
        verbose_name_plural = "learning activities"
        constraints = [models.UniqueConstraint(fields=["subtopic", "display_order"], name="unique_activity_order_per_subtopic")]
        indexes = [models.Index(fields=["subtopic", "status", "display_order"], name="activity_sub_status_ord_idx")]

    def __str__(self) -> str:
        return self.title
