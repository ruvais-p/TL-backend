from rest_framework import serializers

from .models import (
    ActivityProgress, AssessmentAttempt, BadgeAward, CareerOpportunity,
    ChapterProgress, CourseProgress, OpportunityApplication, PointEvent, SubtopicProgress,
)
from .opportunity_validation import validate_opportunity
from .eligibility import evaluate_eligibility, validate_eligibility_rules


class ActivityProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityProgress
        fields = (
            "id",
            "activity",
            "status",
            "progress_percentage",
            "time_spent_seconds",
            "started_at",
            "last_accessed_at",
            "attempt_count",
            "metadata",
            "extra",
            "completed_at",
            "updated_at",
        )
        read_only_fields = ("id", "completed_at", "updated_at", "started_at", "last_accessed_at")


class SubtopicProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubtopicProgress
        fields = tuple(field.name for field in SubtopicProgress._meta.fields)


class ChapterProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChapterProgress
        fields = tuple(field.name for field in ChapterProgress._meta.fields)


class CourseProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseProgress
        fields = tuple(field.name for field in CourseProgress._meta.fields)


class ProgressUpsertSerializer(serializers.Serializer):
    activity = serializers.UUIDField()
    progress_percentage = serializers.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2, required=False)
    time_spent_seconds = serializers.IntegerField(min_value=0, required=False, default=0)
    metadata = serializers.JSONField(required=False, default=dict)
    status = serializers.CharField(required=False, default="in_progress")
    extra = serializers.JSONField(required=False, default=dict)
    event = serializers.CharField(required=False, allow_blank=True)


class PointEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointEvent
        fields = ("id", "reason", "points", "created_at")


class BadgeAwardSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_code_display", read_only=True)

    class Meta:
        model = BadgeAward
        fields = ("id", "code", "label", "created_at")


class CareerOpportunitySerializer(serializers.ModelSerializer):
    employment_type_label = serializers.CharField(
        source="get_employment_type_display", read_only=True
    )
    workplace_mode_label = serializers.CharField(
        source="get_workplace_mode_display", read_only=True
    )
    company_logo_url = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(read_only=True)
    eligibility = serializers.SerializerMethodField()

    class Meta:
        model = CareerOpportunity
        fields = (
            "id",
            "title",
            "company_name",
            "company_website",
            "company_logo_url",
            "summary",
            "description_markdown",
            "employment_type",
            "employment_type_label",
            "workplace_mode",
            "workplace_mode_label",
            "physical_location",
            "remote_region",
            "openings",
            "compensation_disclosure",
            "compensation_currency",
            "compensation_min",
            "compensation_max",
            "compensation_pay_period",
            "start_date",
            "duration",
            "application_deadline",
            "application_mode",
            "application_url",
            "cover_note_required",
            "resume_required",
            "is_featured",
            "is_open",
            "eligibility",
        )
        read_only_fields = fields

    def get_company_logo_url(self, instance):
        logo = instance.company_logo
        if logo is None:
            return ""
        if logo.cdn_url:
            return logo.cdn_url
        request = self.context.get("request")
        if logo.storage_path and request:
            from django.core.files.storage import default_storage

            return request.build_absolute_uri(default_storage.url(logo.storage_path))
        return ""

    def get_eligibility(self, instance):
        snapshot = self.context["eligibility_snapshot"]
        result = evaluate_eligibility(instance.eligibility_rules, snapshot)
        return {"eligible": result.eligible, "reasons": list(result.reasons)}


class StaffActivityProgressSerializer(serializers.ModelSerializer):
    student_email = serializers.EmailField(
        source="enrollment.student.email", read_only=True
    )
    course_name = serializers.CharField(
        source="enrollment.course.name", read_only=True
    )
    activity_title = serializers.CharField(source="activity.title", read_only=True)

    class Meta:
        model = ActivityProgress
        fields = tuple(field.name for field in ActivityProgress._meta.fields) + (
            "student_email",
            "course_name",
            "activity_title",
        )
        read_only_fields = fields


class StaffPointEventSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    activity_title = serializers.CharField(source="activity.title", read_only=True)

    class Meta:
        model = PointEvent
        fields = tuple(field.name for field in PointEvent._meta.fields) + (
            "user_email",
            "activity_title",
        )
        read_only_fields = fields


class StaffBadgeAwardSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    activity_title = serializers.CharField(source="activity.title", read_only=True)
    label = serializers.CharField(source="get_code_display", read_only=True)

    class Meta:
        model = BadgeAward
        fields = tuple(field.name for field in BadgeAward._meta.fields) + (
            "user_email",
            "activity_title",
            "label",
        )
        read_only_fields = fields


class StaffCareerOpportunitySerializer(serializers.ModelSerializer):
    is_open = serializers.SerializerMethodField()
    employment_type_label = serializers.CharField(
        source="get_employment_type_display", read_only=True
    )
    workplace_mode_label = serializers.CharField(
        source="get_workplace_mode_display", read_only=True
    )

    class Meta:
        model = CareerOpportunity
        fields = "__all__"
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
            "legacy_kind",
            "lifecycle_status",
            "is_published",
            "is_open",
        )

    def validate(self, attrs):
        # Keep the legacy CRUD payload useful while all reads move to structured fields.
        initial = self.initial_data
        if initial.get("summary") and "description_markdown" not in initial:
            attrs["description_markdown"] = initial["summary"]
        if initial.get("url") and "application_url" not in initial:
            attrs["application_url"] = initial["url"]
            attrs["application_mode"] = CareerOpportunity.ApplicationMode.EXTERNAL

        requested_status = initial.get("lifecycle_status") or attrs.get(
            "lifecycle_status",
            getattr(self.instance, "lifecycle_status", CareerOpportunity.LifecycleStatus.DRAFT),
        )
        require_complete = requested_status == CareerOpportunity.LifecycleStatus.PUBLISHED
        errors = validate_opportunity(
            attrs, instance=self.instance, require_complete=require_complete
        )
        rules = attrs.get(
            "eligibility_rules",
            getattr(self.instance, "eligibility_rules", None),
        )
        if rules is None:
            rules = CareerOpportunity._meta.get_field("eligibility_rules").get_default()
        rule_errors = validate_eligibility_rules(rules)
        if rule_errors:
            errors["eligibility_rules"] = rule_errors
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def get_is_open(self, instance):
        return instance.is_open


class LearnerApplicationCreateSerializer(serializers.Serializer):
    contact_phone = serializers.CharField(max_length=40)
    cover_note = serializers.CharField(required=False, allow_blank=True, default="")
    resume = serializers.FileField(required=False)


class LearnerApplicationSerializer(serializers.ModelSerializer):
    opportunity_id = serializers.UUIDField(read_only=True)
    opportunity_title = serializers.CharField(source="opportunity.title", read_only=True)
    company_name = serializers.CharField(source="opportunity.company_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    can_withdraw = serializers.SerializerMethodField()
    has_resume = serializers.SerializerMethodField()

    class Meta:
        model = OpportunityApplication
        fields = (
            "id",
            "opportunity_id",
            "opportunity_title",
            "company_name",
            "submitted_at",
            "updated_at",
            "status",
            "status_label",
            "can_withdraw",
            "has_resume",
        )
        read_only_fields = fields

    def get_can_withdraw(self, instance):
        return instance.status not in OpportunityApplication.TERMINAL_STATUSES

    def get_has_resume(self, instance):
        return hasattr(instance, "resume_document")


class StaffOpportunityApplicationSerializer(serializers.ModelSerializer):
    opportunity_title = serializers.CharField(source="opportunity.title", read_only=True)
    company_name = serializers.CharField(source="opportunity.company_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True)
    has_resume = serializers.SerializerMethodField()

    class Meta:
        model = OpportunityApplication
        fields = (
            "id",
            "opportunity",
            "opportunity_title",
            "company_name",
            "applicant",
            "applicant_name",
            "applicant_email",
            "contact_phone",
            "cover_note",
            "status",
            "status_label",
            "submitted_at",
            "created_at",
            "updated_at",
            "review_notes",
            "reviewed_by_email",
            "reviewed_at",
            "has_resume",
        )
        read_only_fields = fields

    def get_has_resume(self, instance):
        return hasattr(instance, "resume_document")


class ApplicationTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OpportunityApplication.Status.choices)
    review_notes = serializers.CharField(required=False, allow_blank=True)


class ApplicationReviewNoteSerializer(serializers.Serializer):
    review_notes = serializers.CharField(allow_blank=True)


class StaffLegacyAssessmentAttemptSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    activity_title = serializers.CharField(source="activity.title", read_only=True)

    class Meta:
        model = AssessmentAttempt
        fields = tuple(field.name for field in AssessmentAttempt._meta.fields) + (
            "user_email",
            "activity_title",
        )
        read_only_fields = fields
