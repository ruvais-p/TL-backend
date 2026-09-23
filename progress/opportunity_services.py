from django.core.exceptions import ValidationError
from django.db import transaction

from progress.models import CareerOpportunity
from progress.opportunity_validation import validate_opportunity


class OpportunityStateError(ValidationError):
    pass


class OpportunityLifecycleService:
    @staticmethod
    def _locked(opportunity):
        return CareerOpportunity.objects.select_for_update().get(pk=opportunity.pk)

    @classmethod
    @transaction.atomic
    def save_draft(cls, opportunity, **updates):
        locked = cls._locked(opportunity)
        if locked.lifecycle_status == CareerOpportunity.LifecycleStatus.ARCHIVED:
            raise OpportunityStateError("Archived opportunities cannot return to draft.")
        for field, value in updates.items():
            setattr(locked, field, value)
        errors = validate_opportunity(updates, instance=locked, require_complete=False)
        if errors:
            raise ValidationError(errors)
        locked.lifecycle_status = CareerOpportunity.LifecycleStatus.DRAFT
        locked.is_published = False
        locked.save()
        return locked

    @classmethod
    @transaction.atomic
    def publish(cls, opportunity):
        locked = cls._locked(opportunity)
        if locked.lifecycle_status == CareerOpportunity.LifecycleStatus.ARCHIVED:
            raise OpportunityStateError("Archived opportunities cannot be published.")
        errors = validate_opportunity({}, instance=locked, require_complete=True)
        if errors:
            raise ValidationError(errors)
        locked.lifecycle_status = CareerOpportunity.LifecycleStatus.PUBLISHED
        locked.is_published = True
        locked.save(update_fields=["lifecycle_status", "is_published", "updated_at"])
        return locked

    @classmethod
    @transaction.atomic
    def close(cls, opportunity):
        locked = cls._locked(opportunity)
        if locked.lifecycle_status != CareerOpportunity.LifecycleStatus.PUBLISHED:
            raise OpportunityStateError("Only published opportunities can be closed.")
        locked.lifecycle_status = CareerOpportunity.LifecycleStatus.CLOSED
        locked.is_published = False
        locked.save(update_fields=["lifecycle_status", "is_published", "updated_at"])
        return locked

    @classmethod
    @transaction.atomic
    def archive(cls, opportunity):
        locked = cls._locked(opportunity)
        if locked.lifecycle_status == CareerOpportunity.LifecycleStatus.ARCHIVED:
            raise OpportunityStateError("The opportunity is already archived.")
        locked.lifecycle_status = CareerOpportunity.LifecycleStatus.ARCHIVED
        locked.is_published = False
        locked.save(update_fields=["lifecycle_status", "is_published", "updated_at"])
        return locked

    @staticmethod
    def ensure_accepting_applications(opportunity):
        if not opportunity.is_open:
            raise OpportunityStateError(
                "This opportunity is not open for new applications."
            )
