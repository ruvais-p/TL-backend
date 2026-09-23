from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from progress.application_services import (
    ApplicationSubmissionError,
    DuplicateApplicationError,
    OpportunityApplicationService,
)
from progress.models import CareerOpportunity, OpportunityApplication
from students.models import StudentGroup, StudentGroupMember


User = get_user_model()


class OpportunityApplicationSubmissionTests(TestCase):
    def setUp(self):
        self.learner = User.objects.create_user(
            email="applicant@example.com",
            username="applicant",
            first_name="Asha",
            last_name="Rao",
            password="pass",
        )
        self.opportunity = CareerOpportunity.objects.create(
            title="Internal internship",
            company_name="Tella Labs",
            lifecycle_status=CareerOpportunity.LifecycleStatus.PUBLISHED,
            is_published=True,
            application_mode=CareerOpportunity.ApplicationMode.INTERNAL,
            application_deadline=timezone.now() + timedelta(days=2),
        )

    def submit(self, **overrides):
        values = {
            "opportunity": self.opportunity,
            "applicant": self.learner,
            "contact_phone": "+91 90000 00000",
            "cover_note": "I am interested.",
        }
        values.update(overrides)
        return OpportunityApplicationService.submit(**values)

    def test_valid_submission_snapshots_identity(self):
        application = self.submit()

        self.assertEqual(application.status, OpportunityApplication.Status.SUBMITTED)
        self.assertEqual(application.applicant_name, "Asha Rao")
        self.assertEqual(application.applicant_email, self.learner.email)

    def test_duplicate_submission_creates_no_second_record(self):
        self.submit()
        with self.assertRaises(DuplicateApplicationError):
            self.submit()
        self.assertEqual(OpportunityApplication.objects.count(), 1)

    def test_deadline_is_rechecked_at_submission(self):
        self.opportunity.application_deadline = timezone.now() - timedelta(seconds=1)
        self.opportunity.save(update_fields=["application_deadline"])

        with self.assertRaises(ApplicationSubmissionError) as context:
            self.submit()

        self.assertEqual(context.exception.code, "not_open")
        self.assertEqual(OpportunityApplication.objects.count(), 0)

    def test_current_audience_and_eligibility_are_rechecked(self):
        group = StudentGroup.objects.create(
            name="Grade 12", code="grade-12", grade="12", academic_year=2026
        )
        StudentGroupMember.objects.create(student_group=group, student=self.learner)
        self.opportunity.eligibility_rules = {
            "version": 1,
            "match": "ALL",
            "conditions": [
                {"fact": "GROUP_GRADE", "operator": "IN", "values": ["11"]}
            ],
        }
        self.opportunity.save(update_fields=["eligibility_rules"])

        with self.assertRaises(ApplicationSubmissionError) as context:
            self.submit()

        self.assertEqual(context.exception.code, "ineligible")
        self.assertTrue(context.exception.reasons)
        self.assertEqual(OpportunityApplication.objects.count(), 0)

    def test_outside_audience_and_external_modes_are_rejected(self):
        group = StudentGroup.objects.create(
            name="Private", code="private", grade="10", academic_year=2026
        )
        self.opportunity.audience_scope = CareerOpportunity.AudienceScope.SELECTED_GROUPS
        self.opportunity.save(update_fields=["audience_scope"])
        self.opportunity.audience_groups.add(group)
        with self.assertRaises(ApplicationSubmissionError) as context:
            self.submit()
        self.assertEqual(context.exception.code, "not_available")

        self.opportunity.audience_scope = CareerOpportunity.AudienceScope.ALL_LEARNERS
        self.opportunity.application_mode = CareerOpportunity.ApplicationMode.EXTERNAL
        self.opportunity.save(update_fields=["audience_scope", "application_mode"])
        with self.assertRaises(ApplicationSubmissionError) as context:
            self.submit()
        self.assertEqual(context.exception.code, "external_application")

    def test_required_fields_fail_without_partial_application(self):
        self.opportunity.cover_note_required = True
        self.opportunity.resume_required = True
        self.opportunity.save(update_fields=["cover_note_required", "resume_required"])

        with self.assertRaises(ApplicationSubmissionError):
            self.submit(cover_note="", resume=None)

        self.assertEqual(OpportunityApplication.objects.count(), 0)
