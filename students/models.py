import uuid

from django.conf import settings
from django.db import models

from curriculum.models import Course, CourseVersion


class TimestampedUUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class StudentGroup(TimestampedUUIDModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        ARCHIVED = "ARCHIVED", "Archived"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=80, unique=True)
    grade = models.CharField(max_length=40, blank=True)
    academic_year = models.PositiveIntegerField(db_index=True)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="teaching_student_groups",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        ordering = ["-academic_year", "grade", "name"]
        permissions = [("manage_student_groups", "Can manage student groups")]
        indexes = [models.Index(fields=["teacher", "status", "academic_year"], name="studentgrp_teacher_status_yr")]

    def __str__(self) -> str:
        return f"{self.name} ({self.academic_year})"


class StudentGroupMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, related_name="memberships")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="student_group_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student_group", "student"], name="unique_student_group_member")]
        indexes = [models.Index(fields=["student", "student_group"], name="student_member_group_idx")]


class Enrollment(TimestampedUUIDModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        SUSPENDED = "SUSPENDED", "Suspended"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="course_enrollments")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="student_enrollments")
    course_version = models.ForeignKey(CourseVersion, on_delete=models.PROTECT, related_name="student_enrollments")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-enrolled_at"]
        constraints = [
            models.UniqueConstraint(fields=["student", "course"], condition=models.Q(status="ACTIVE"), name="unique_active_student_course"),
            models.UniqueConstraint(fields=["student", "course_version"], condition=models.Q(status="ACTIVE"), name="unique_active_student_version"),
        ]
        permissions = [("manage_students", "Can manage students")]
        indexes = [
            models.Index(fields=["student", "status"], name="enroll_student_status_idx"),
            models.Index(fields=["course", "status"], name="enroll_course_status_idx"),
            models.Index(fields=["course_version", "status"], name="enroll_version_status_idx"),
        ]

    @property
    def is_accessible(self) -> bool:
        from django.utils import timezone
        return self.status == self.Status.ACTIVE and (self.expires_at is None or self.expires_at > timezone.now())


class CourseAssignment(TimestampedUUIDModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="assignments")
    course_version = models.ForeignKey(CourseVersion, on_delete=models.PROTECT, related_name="assignments")
    student_group = models.ForeignKey(StudentGroup, on_delete=models.PROTECT, null=True, blank=True, related_name="course_assignments")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="individual_course_assignments")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="course_assignments_created")
    assigned_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(student_group__isnull=False, student__isnull=True) | models.Q(student_group__isnull=True, student__isnull=False)),
                name="assignment_exactly_one_target",
            )
        ]
        permissions = [("assign_course", "Can assign courses to students or groups")]
        indexes = [models.Index(fields=["student_group", "status"], name="assignment_group_status_idx"), models.Index(fields=["student", "status"], name="assignment_student_status_idx")]


class ExternalUserMapping(models.Model):
    class Provider(models.TextChoices):
        MOODLE = "MOODLE", "Moodle"
        CANVAS = "CANVAS", "Canvas"
        MOBILE_APP = "MOBILE_APP", "Mobile app"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_mappings")
    provider = models.CharField(max_length=30, choices=Provider.choices)
    external_user_id = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "external_user_id"], name="unique_external_provider_user")]
        indexes = [models.Index(fields=["user", "provider"], name="external_user_provider_idx")]
