from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from progress.models import CareerOpportunity, OpportunityApplication


User = get_user_model()


class OpportunityApplicationModelTests(TestCase):
    def setUp(self):
        self.learner = User.objects.create_user(
            email="opportunity-learner@example.com", password="StrongPass123!"
        )
        self.opportunity = CareerOpportunity.objects.create(title="Data internship")

    def application(self, **overrides):
        values = {
            "opportunity": self.opportunity,
            "applicant": self.learner,
            "applicant_name": "Opportunity Learner",
            "applicant_email": self.learner.email,
            "contact_phone": "+91 90000 00000",
        }
        values.update(overrides)
        return OpportunityApplication.objects.create(**values)

    def test_duplicate_application_is_rejected_by_database(self):
        self.application()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.application()

        self.assertEqual(OpportunityApplication.objects.count(), 1)

    def test_only_outcome_and_withdrawn_statuses_are_terminal(self):
        application = self.application()
        for active_status in (
            OpportunityApplication.Status.SUBMITTED,
            OpportunityApplication.Status.UNDER_REVIEW,
            OpportunityApplication.Status.SHORTLISTED,
        ):
            application.status = active_status
            self.assertFalse(application.is_terminal)

        for terminal_status in OpportunityApplication.TERMINAL_STATUSES:
            application.status = terminal_status
            self.assertTrue(application.is_terminal)
