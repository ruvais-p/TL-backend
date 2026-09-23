from django.db import IntegrityError, transaction
from django.utils import timezone

from progress.eligibility import (
    LearnerFactSnapshot,
    evaluate_eligibility,
    validate_eligibility_rules,
)
from progress.models import CareerOpportunity, OpportunityApplication
from progress.opportunity_services import OpportunityLifecycleService
from progress.private_documents import ResumeValidationError, store_resume, validate_resume


class ApplicationSubmissionError(Exception):
    def __init__(self, message, *, code="invalid_application", reasons=()):
        super().__init__(message)
        self.code = code
        self.reasons = tuple(reasons)


class DuplicateApplicationError(ApplicationSubmissionError):
    def __init__(self):
        super().__init__(
            "You have already applied for this opportunity.",
            code="duplicate_application",
        )


class ApplicationTransitionError(Exception):
    pass


class OpportunityApplicationService:
    STAFF_TRANSITIONS = {
        OpportunityApplication.Status.SUBMITTED: {
            OpportunityApplication.Status.UNDER_REVIEW,
            OpportunityApplication.Status.SHORTLISTED,
            OpportunityApplication.Status.ACCEPTED,
            OpportunityApplication.Status.REJECTED,
        },
        OpportunityApplication.Status.UNDER_REVIEW: {
            OpportunityApplication.Status.SHORTLISTED,
            OpportunityApplication.Status.ACCEPTED,
            OpportunityApplication.Status.REJECTED,
        },
        OpportunityApplication.Status.SHORTLISTED: {
            OpportunityApplication.Status.UNDER_REVIEW,
            OpportunityApplication.Status.ACCEPTED,
            OpportunityApplication.Status.REJECTED,
        },
    }
    @staticmethod
    def _is_in_audience(opportunity, applicant):
        if opportunity.audience_scope == CareerOpportunity.AudienceScope.ALL_LEARNERS:
            return True
        return opportunity.audience_groups.filter(
            memberships__student=applicant
        ).exists()

    @classmethod
    @transaction.atomic
    def submit(
        cls,
        *,
        opportunity,
        applicant,
        contact_phone,
        cover_note="",
        resume=None,
    ):
        if resume is not None:
            try:
                validate_resume(resume)
            except ResumeValidationError as exc:
                raise ApplicationSubmissionError(str(exc), code="invalid_resume") from exc
        locked = CareerOpportunity.objects.select_for_update().get(pk=opportunity.pk)
        if locked.application_mode != CareerOpportunity.ApplicationMode.INTERNAL:
            raise ApplicationSubmissionError(
                "This opportunity accepts applications on an external site.",
                code="external_application",
            )
        try:
            OpportunityLifecycleService.ensure_accepting_applications(locked)
        except Exception as exc:
            raise ApplicationSubmissionError(
                "This opportunity is not open for new applications.", code="not_open"
            ) from exc
        if not cls._is_in_audience(locked, applicant):
            raise ApplicationSubmissionError(
                "This opportunity is unavailable.", code="not_available"
            )
        rule_errors = validate_eligibility_rules(locked.eligibility_rules)
        if rule_errors:
            raise ApplicationSubmissionError(
                "Eligibility requirements are unavailable.", code="ineligible"
            )
        eligibility = evaluate_eligibility(
            locked.eligibility_rules, LearnerFactSnapshot.for_user(applicant)
        )
        if not eligibility.eligible:
            raise ApplicationSubmissionError(
                "You do not currently meet the eligibility requirements.",
                code="ineligible",
                reasons=eligibility.reasons,
            )
        if not contact_phone.strip():
            raise ApplicationSubmissionError(
                "A contact phone number is required.", code="contact_phone_required"
            )
        if locked.cover_note_required and not cover_note.strip():
            raise ApplicationSubmissionError(
                "A cover note is required.", code="cover_note_required"
            )
        if locked.resume_required and resume is None:
            raise ApplicationSubmissionError(
                "A resume is required.", code="resume_required"
            )
        if OpportunityApplication.objects.filter(
            opportunity=locked, applicant=applicant
        ).exists():
            raise DuplicateApplicationError()

        try:
            with transaction.atomic():
                application = OpportunityApplication.objects.create(
                    opportunity=locked,
                    applicant=applicant,
                    applicant_name=applicant.display_name,
                    applicant_email=applicant.email,
                    contact_phone=contact_phone.strip(),
                    cover_note=cover_note.strip(),
                )
        except IntegrityError as exc:
            raise DuplicateApplicationError() from exc
        if resume is not None:
            try:
                store_resume(application=application, upload=resume)
            except ResumeValidationError as exc:
                raise ApplicationSubmissionError(str(exc), code="invalid_resume") from exc
        return application

    @classmethod
    @transaction.atomic
    def transition_by_staff(cls, *, application, actor, new_status, review_notes=None):
        if not actor.has_perm("progress.review_opportunityapplication"):
            raise ApplicationTransitionError(
                "Application review permission is required."
            )
        locked = OpportunityApplication.objects.select_for_update().get(
            pk=application.pk
        )
        allowed = cls.STAFF_TRANSITIONS.get(locked.status, set())
        if new_status not in allowed:
            raise ApplicationTransitionError(
                f"Cannot transition an application from {locked.status} to {new_status}."
            )
        locked.status = new_status
        if review_notes is not None:
            locked.review_notes = review_notes.strip()
        locked.reviewed_by = actor
        locked.reviewed_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "review_notes",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
        return locked

    @staticmethod
    @transaction.atomic
    def withdraw_by_applicant(*, application, actor):
        locked = OpportunityApplication.objects.select_for_update().get(
            pk=application.pk
        )
        if locked.applicant_id != actor.id:
            raise ApplicationTransitionError("Only the applicant can withdraw.")
        if locked.status not in {
            OpportunityApplication.Status.SUBMITTED,
            OpportunityApplication.Status.UNDER_REVIEW,
            OpportunityApplication.Status.SHORTLISTED,
        }:
            raise ApplicationTransitionError(
                f"Cannot withdraw an application in {locked.status} status."
            )
        locked.status = OpportunityApplication.Status.WITHDRAWN
        locked.save(update_fields=["status", "updated_at"])
        return locked

    @staticmethod
    @transaction.atomic
    def update_review_notes(*, application, actor, review_notes):
        if not actor.has_perm("progress.review_opportunityapplication"):
            raise ApplicationTransitionError(
                "Application review permission is required."
            )
        locked = OpportunityApplication.objects.select_for_update().get(
            pk=application.pk
        )
        locked.review_notes = review_notes.strip()
        locked.reviewed_by = actor
        locked.reviewed_at = timezone.now()
        locked.save(
            update_fields=["review_notes", "reviewed_by", "reviewed_at", "updated_at"]
        )
        return locked
