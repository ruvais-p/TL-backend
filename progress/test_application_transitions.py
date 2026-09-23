from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase

from accounts.constants import GroupName
from progress.application_services import (
    ApplicationTransitionError,
    OpportunityApplicationService,
)
from progress.models import CareerOpportunity, OpportunityApplication


User = get_user_model()


class OpportunityApplicationTransitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)

    def setUp(self):
        self.learner = User.objects.create_user(email="transition-learner@example.com", password="pass")
        self.reviewer = User.objects.create_user(email="reviewer@example.com", password="pass")
        self.reviewer.groups.add(Group.objects.get(name=GroupName.ADMIN))
        self.outsider = User.objects.create_user(email="outsider@example.com", password="pass")
        opportunity = CareerOpportunity.objects.create(title="Transition role")
        self.application = OpportunityApplication.objects.create(
            opportunity=opportunity,
            applicant=self.learner,
            applicant_name="Learner",
            applicant_email=self.learner.email,
            contact_phone="123",
        )

    def set_status(self, status):
        self.application.status = status
        self.application.save(update_fields=["status"])

    def test_every_documented_staff_transition_and_audit_fields(self):
        for origin, destinations in OpportunityApplicationService.STAFF_TRANSITIONS.items():
            for destination in destinations:
                self.set_status(origin)
                transitioned = OpportunityApplicationService.transition_by_staff(
                    application=self.application,
                    actor=self.reviewer,
                    new_status=destination,
                    review_notes="Strong candidate",
                )
                self.assertEqual(transitioned.status, destination)
                self.assertEqual(transitioned.reviewed_by, self.reviewer)
                self.assertIsNotNone(transitioned.reviewed_at)
                self.assertEqual(transitioned.review_notes, "Strong candidate")

    def test_terminal_statuses_reject_staff_and_learner_transitions(self):
        for terminal in OpportunityApplication.TERMINAL_STATUSES:
            self.set_status(terminal)
            with self.assertRaises(ApplicationTransitionError):
                OpportunityApplicationService.transition_by_staff(
                    application=self.application,
                    actor=self.reviewer,
                    new_status=OpportunityApplication.Status.UNDER_REVIEW,
                )
            with self.assertRaises(ApplicationTransitionError):
                OpportunityApplicationService.withdraw_by_applicant(
                    application=self.application, actor=self.learner
                )

    def test_applicant_can_withdraw_each_active_status(self):
        for active in (
            OpportunityApplication.Status.SUBMITTED,
            OpportunityApplication.Status.UNDER_REVIEW,
            OpportunityApplication.Status.SHORTLISTED,
        ):
            self.set_status(active)
            withdrawn = OpportunityApplicationService.withdraw_by_applicant(
                application=self.application, actor=self.learner
            )
            self.assertEqual(withdrawn.status, OpportunityApplication.Status.WITHDRAWN)

    def test_unauthorized_reviewer_and_other_learner_are_denied(self):
        with self.assertRaises(ApplicationTransitionError):
            OpportunityApplicationService.transition_by_staff(
                application=self.application,
                actor=self.outsider,
                new_status=OpportunityApplication.Status.UNDER_REVIEW,
            )
        with self.assertRaises(ApplicationTransitionError):
            OpportunityApplicationService.withdraw_by_applicant(
                application=self.application, actor=self.outsider
            )
