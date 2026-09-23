import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from progress.models import CareerOpportunity, OpportunityApplication


User = get_user_model()


class LearnerApplicationAPITests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings_override = self.settings(PRIVATE_DOCUMENT_ROOT=self.temporary.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.learner = User.objects.create_user(
            email="application-api@example.com",
            username="application-api",
            first_name="Asha",
            password="pass",
        )
        self.other = User.objects.create_user(email="other-api@example.com", password="pass")
        self.opportunity = CareerOpportunity.objects.create(
            title="Internal role",
            company_name="Tella Labs",
            lifecycle_status=CareerOpportunity.LifecycleStatus.PUBLISHED,
            application_mode=CareerOpportunity.ApplicationMode.INTERNAL,
            resume_required=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.learner)

    def submit(self):
        return self.client.post(
            f"/api/v1/career/opportunities/{self.opportunity.id}/applications/",
            {
                "contact_phone": "12345",
                "cover_note": "Hello",
                "resume": SimpleUploadedFile(
                    "resume.pdf", b"%PDF resume", content_type="application/pdf"
                ),
                "eligibility": True,
                "applicant": str(self.other.id),
            },
            format="multipart",
        )

    def test_internal_submission_uses_authenticated_identity(self):
        response = self.submit()

        self.assertEqual(response.status_code, 201, response.data)
        application = OpportunityApplication.objects.get()
        self.assertEqual(application.applicant, self.learner)
        self.assertNotIn("applicant_email", response.data)

    def test_history_is_learner_isolated_and_private(self):
        own = OpportunityApplication.objects.create(
            opportunity=self.opportunity,
            applicant=self.learner,
            applicant_name="Asha",
            applicant_email=self.learner.email,
            contact_phone="123",
            review_notes="Private reviewer note",
        )
        OpportunityApplication.objects.create(
            opportunity=self.opportunity,
            applicant=self.other,
            applicant_name="Other",
            applicant_email=self.other.email,
            contact_phone="456",
        )

        response = self.client.get("/api/v1/career/applications/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [str(own.id)])
        self.assertNotIn("review_notes", response.data[0])
        self.assertNotIn("reviewed_by", response.data[0])

    def test_owner_can_download_resume_but_other_learner_gets_404(self):
        application_id = self.submit().data["id"]

        owner = self.client.get(
            f"/api/v1/career/applications/{application_id}/resume/"
        )
        self.assertEqual(owner.status_code, 200)

        self.client.force_authenticate(self.other)
        denied = self.client.get(
            f"/api/v1/career/applications/{application_id}/resume/"
        )
        self.assertEqual(denied.status_code, 404)

    def test_active_application_can_withdraw_but_terminal_cannot(self):
        application = OpportunityApplication.objects.create(
            opportunity=self.opportunity,
            applicant=self.learner,
            applicant_name="Asha",
            applicant_email=self.learner.email,
            contact_phone="123",
        )
        withdrawn = self.client.post(
            f"/api/v1/career/applications/{application.id}/withdraw/"
        )
        self.assertEqual(withdrawn.status_code, 200)
        second = self.client.post(
            f"/api/v1/career/applications/{application.id}/withdraw/"
        )
        self.assertEqual(second.status_code, 409)

    def test_external_handoff_creates_no_internal_application(self):
        self.opportunity.application_mode = CareerOpportunity.ApplicationMode.EXTERNAL
        self.opportunity.application_url = "https://example.com/apply"
        self.opportunity.save(update_fields=["application_mode", "application_url"])

        response = self.client.post(
            f"/api/v1/career/opportunities/{self.opportunity.id}/applications/",
            {"contact_phone": "123"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "external_application")
        self.assertEqual(OpportunityApplication.objects.count(), 0)
