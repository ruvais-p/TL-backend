from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from progress.models import CareerOpportunity
from progress.opportunity_services import (
    OpportunityLifecycleService,
    OpportunityStateError,
)


class OpportunityLifecycleTests(TestCase):
    def valid_draft(self, **overrides):
        values = {
            "title": "Remote internship",
            "company_name": "Tella Labs",
            "summary": "A useful role",
            "description_markdown": "## The role\n\nBuild useful things.",
            "employment_type": CareerOpportunity.EmploymentType.INTERNSHIP,
            "workplace_mode": CareerOpportunity.WorkplaceMode.REMOTE,
            "remote_region": "India",
            "application_mode": CareerOpportunity.ApplicationMode.INTERNAL,
            "application_deadline": timezone.now() + timedelta(days=7),
        }
        values.update(overrides)
        return CareerOpportunity.objects.create(**values)

    def test_incomplete_draft_cannot_publish(self):
        draft = CareerOpportunity.objects.create(title="Incomplete")

        with self.assertRaises(ValidationError) as context:
            OpportunityLifecycleService.publish(draft)

        self.assertIn("company_name", context.exception.message_dict)
        draft.refresh_from_db()
        self.assertEqual(draft.lifecycle_status, CareerOpportunity.LifecycleStatus.DRAFT)

    def test_publish_close_and_archive_synchronize_legacy_flag(self):
        opportunity = OpportunityLifecycleService.publish(self.valid_draft())
        self.assertTrue(opportunity.is_open)
        self.assertTrue(opportunity.is_published)

        opportunity = OpportunityLifecycleService.close(opportunity)
        self.assertFalse(opportunity.is_open)
        self.assertFalse(opportunity.is_published)

        opportunity = OpportunityLifecycleService.archive(opportunity)
        self.assertEqual(
            opportunity.lifecycle_status, CareerOpportunity.LifecycleStatus.ARCHIVED
        )
        with self.assertRaises(OpportunityStateError):
            OpportunityLifecycleService.publish(opportunity)

    def test_expired_published_opportunity_is_not_open(self):
        opportunity = self.valid_draft(
            lifecycle_status=CareerOpportunity.LifecycleStatus.PUBLISHED,
            is_published=True,
            application_deadline=timezone.now() - timedelta(seconds=1),
        )

        self.assertFalse(opportunity.is_open)
        with self.assertRaises(OpportunityStateError):
            OpportunityLifecycleService.ensure_accepting_applications(opportunity)

    def test_closed_and_archived_opportunities_reject_applications(self):
        for lifecycle in (
            CareerOpportunity.LifecycleStatus.CLOSED,
            CareerOpportunity.LifecycleStatus.ARCHIVED,
        ):
            opportunity = self.valid_draft(lifecycle_status=lifecycle)
            with self.assertRaises(OpportunityStateError):
                OpportunityLifecycleService.ensure_accepting_applications(opportunity)
