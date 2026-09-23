import uuid

from django.conf import settings
from django.db import models

from curriculum.models import Chapter, LearningActivity, Subtopic
from students.models import Enrollment


class TimestampedUUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CourseProgress(TimestampedUUIDModel):
    enrollment = models.OneToOneField(
        Enrollment, on_delete=models.CASCADE, related_name="course_progress"
    )
    percent_complete = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default="NOT_STARTED", db_index=True)
    completed_chapters = models.PositiveIntegerField(default=0)
    total_chapters = models.PositiveIntegerField(default=0)
    average_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("view_all_student_progress", "Can view all student progress"),
            ("view_assigned_student_progress", "Can view assigned student progress"),
        ]


class ChapterProgress(TimestampedUUIDModel):
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="chapter_progress"
    )
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE)
    percent_complete = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default="NOT_STARTED", db_index=True)
    completed_subtopics = models.PositiveIntegerField(default=0)
    total_subtopics = models.PositiveIntegerField(default=0)
    case_study_status = models.CharField(max_length=20, default="NOT_STARTED")
    learning_check_status = models.CharField(max_length=20, default="NOT_STARTED")
    learning_check_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("enrollment", "chapter")


class SubtopicProgress(TimestampedUUIDModel):
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="subtopic_progress"
    )
    subtopic = models.ForeignKey(Subtopic, on_delete=models.CASCADE)
    percent_complete = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, default="NOT_STARTED", db_index=True)
    completed_activities = models.PositiveIntegerField(default=0)
    total_required_activities = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("enrollment", "subtopic")


class ActivityProgress(TimestampedUUIDModel):
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="activity_progress"
    )
    activity = models.ForeignKey(LearningActivity, on_delete=models.CASCADE)
    status = models.CharField(max_length=32, default="not_started")
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("enrollment", "activity")


class AssessmentAttempt(TimestampedUUIDModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assessment_attempts"
    )
    activity = models.ForeignKey(LearningActivity, on_delete=models.CASCADE)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)


class AssessmentAnswer(TimestampedUUIDModel):
    attempt = models.ForeignKey(
        AssessmentAttempt, on_delete=models.CASCADE, related_name="answers"
    )
    question_key = models.CharField(max_length=80)
    answer = models.JSONField(default=dict)
    is_correct = models.BooleanField(null=True, blank=True)


class PointEvent(TimestampedUUIDModel):
    class Reason(models.TextChoices):
        LOAD_SAMPLE = "load_sample", "Loaded sample"
        EXPLORE_SLOPES = "explore_slopes", "Explored both slopes"
        REACH_PEAK = "reach_peak", "Reached the peak"
        EXPORT_REPORT = "export_report", "Exported report"

    POINTS = {
        Reason.LOAD_SAMPLE: 10,
        Reason.EXPLORE_SLOPES: 25,
        Reason.REACH_PEAK: 50,
        Reason.EXPORT_REPORT: 20,
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="point_events"
    )
    activity = models.ForeignKey(
        LearningActivity, on_delete=models.CASCADE, related_name="point_events"
    )
    reason = models.CharField(max_length=32, choices=Reason.choices)
    points = models.PositiveIntegerField()

    class Meta:
        unique_together = ("user", "activity", "reason")


class BadgeAward(TimestampedUUIDModel):
    class Code(models.TextChoices):
        FIRST_PEAK = "first_peak", "First Peak"
        SLOPE_READER = "slope_reader", "Slope Reader"
        BUSINESS_OPTIMISER = "business_optimiser", "Business Optimiser"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges"
    )
    activity = models.ForeignKey(
        LearningActivity, on_delete=models.CASCADE, related_name="badges"
    )
    code = models.CharField(max_length=40, choices=Code.choices)

    class Meta:
        unique_together = ("user", "activity", "code")


def empty_eligibility_rules():
    return {"version": 1, "match": "ALL", "conditions": []}


class CareerOpportunity(TimestampedUUIDModel):
    class EmploymentType(models.TextChoices):
        INTERNSHIP = "INTERNSHIP", "Internship"
        FULL_TIME = "FULL_TIME", "Full time"
        PART_TIME = "PART_TIME", "Part time"
        CONTRACT = "CONTRACT", "Contract"
        APPRENTICESHIP = "APPRENTICESHIP", "Apprenticeship"
        PROJECT = "PROJECT", "Project"

    class WorkplaceMode(models.TextChoices):
        REMOTE = "REMOTE", "Remote"
        HYBRID = "HYBRID", "Hybrid"
        IN_OFFICE = "IN_OFFICE", "In office"

    class LifecycleStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        CLOSED = "CLOSED", "Closed"
        ARCHIVED = "ARCHIVED", "Archived"

    class ApplicationMode(models.TextChoices):
        INTERNAL = "INTERNAL", "Internal"
        EXTERNAL = "EXTERNAL", "External"

    class AudienceScope(models.TextChoices):
        ALL_LEARNERS = "ALL_LEARNERS", "All learners"
        SELECTED_GROUPS = "SELECTED_GROUPS", "Selected groups"

    class CompensationDisclosure(models.TextChoices):
        NOT_DISCLOSED = "NOT_DISCLOSED", "Not disclosed"
        PAID = "PAID", "Paid"
        UNPAID = "UNPAID", "Unpaid"

    class PayPeriod(models.TextChoices):
        HOUR = "HOUR", "Per hour"
        DAY = "DAY", "Per day"
        WEEK = "WEEK", "Per week"
        MONTH = "MONTH", "Per month"
        YEAR = "YEAR", "Per year"
        PROJECT = "PROJECT", "Per project"

    title = models.CharField(max_length=200)
    company_name = models.CharField(max_length=200, blank=True)
    company_website = models.URLField(max_length=2048, blank=True)
    company_logo = models.ForeignKey(
        "media_library.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="career_opportunities",
    )
    kind = models.CharField(max_length=40, default="internship")
    legacy_kind = models.CharField(max_length=40, blank=True)
    employment_type = models.CharField(
        max_length=24, choices=EmploymentType.choices, default=EmploymentType.INTERNSHIP
    )
    workplace_mode = models.CharField(
        max_length=24, choices=WorkplaceMode.choices, default=WorkplaceMode.REMOTE
    )
    lifecycle_status = models.CharField(
        max_length=20,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.DRAFT,
        db_index=True,
    )
    summary = models.TextField(blank=True)
    description_markdown = models.TextField(blank=True)
    openings = models.PositiveIntegerField(null=True, blank=True)
    physical_location = models.CharField(max_length=255, blank=True)
    remote_region = models.CharField(max_length=255, blank=True)
    compensation_disclosure = models.CharField(
        max_length=20,
        choices=CompensationDisclosure.choices,
        default=CompensationDisclosure.NOT_DISCLOSED,
    )
    compensation_currency = models.CharField(max_length=3, blank=True)
    compensation_min = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    compensation_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    compensation_pay_period = models.CharField(
        max_length=20, choices=PayPeriod.choices, blank=True
    )
    start_date = models.DateField(null=True, blank=True)
    duration = models.CharField(max_length=120, blank=True)
    application_deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    application_mode = models.CharField(
        max_length=20,
        choices=ApplicationMode.choices,
        default=ApplicationMode.INTERNAL,
    )
    application_url = models.URLField(max_length=2048, blank=True)
    cover_note_required = models.BooleanField(default=False)
    resume_required = models.BooleanField(default=False)
    audience_scope = models.CharField(
        max_length=24,
        choices=AudienceScope.choices,
        default=AudienceScope.ALL_LEARNERS,
        db_index=True,
    )
    audience_groups = models.ManyToManyField(
        "students.StudentGroup", blank=True, related_name="career_opportunities"
    )
    eligibility_rules = models.JSONField(
        default=empty_eligibility_rules, blank=True
    )
    url = models.URLField(blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["lifecycle_status", "application_deadline"],
                name="opp_lifecycle_deadline_idx",
            ),
            models.Index(
                fields=["employment_type", "workplace_mode"],
                name="opp_employment_work_idx",
            ),
            models.Index(
                fields=["is_featured", "created_at"], name="opp_featured_created_idx"
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        from django.utils import timezone

        return self.lifecycle_status == self.LifecycleStatus.PUBLISHED and (
            self.application_deadline is None
            or self.application_deadline > timezone.now()
        )


class OpportunityApplication(TimestampedUUIDModel):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        SHORTLISTED = "SHORTLISTED", "Shortlisted"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    TERMINAL_STATUSES = frozenset({Status.ACCEPTED, Status.REJECTED, Status.WITHDRAWN})

    opportunity = models.ForeignKey(
        CareerOpportunity, on_delete=models.PROTECT, related_name="applications"
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opportunity_applications",
    )
    applicant_name = models.CharField(max_length=255)
    applicant_email = models.EmailField()
    contact_phone = models.CharField(max_length=40)
    cover_note = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunity_applications_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        permissions = [
            ("review_opportunityapplication", "Can review opportunity applications"),
            ("download_opportunityapplicationdocument", "Can download application documents"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["opportunity", "applicant"],
                name="unique_opportunity_applicant",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "SUBMITTED",
                        "UNDER_REVIEW",
                        "SHORTLISTED",
                        "ACCEPTED",
                        "REJECTED",
                        "WITHDRAWN",
                    ]
                ),
                name="valid_opportunity_application_status",
            ),
        ]
        indexes = [
            models.Index(
                fields=["opportunity", "status", "submitted_at"],
                name="oppapp_opp_status_date_idx",
            ),
            models.Index(
                fields=["applicant", "status"], name="oppapp_applicant_status_idx"
            ),
        ]

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL_STATUSES

    def __str__(self):
        return f"{self.applicant_email} — {self.opportunity.title}"


class OpportunityApplicationDocument(TimestampedUUIDModel):
    application = models.OneToOneField(
        OpportunityApplication,
        on_delete=models.PROTECT,
        related_name="resume_document",
    )
    storage_key = models.CharField(max_length=255, unique=True)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120)
    file_size = models.PositiveBigIntegerField()
    checksum_sha256 = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Resume for {self.application.applicant_email}"
