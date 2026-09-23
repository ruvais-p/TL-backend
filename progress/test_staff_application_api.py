import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.constants import GroupName
from progress.application_services import OpportunityApplicationService
from progress.models import CareerOpportunity, OpportunityApplication


User = get_user_model()


class StaffApplicationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        override = self.settings(PRIVATE_DOCUMENT_ROOT=self.temporary.name)
        override.enable()
        self.addCleanup(override.disable)
        self.admin = User.objects.create_user(email="staff-reviewer@example.com", password="pass")
        self.admin.groups.add(Group.objects.get(name=GroupName.ADMIN))
        self.teacher = User.objects.create_user(email="staff-no-review@example.com", password="pass")
        self.teacher.groups.add(Group.objects.get(name=GroupName.TEACHER))
        self.learner = User.objects.create_user(email="candidate@example.com", first_name="Asha", password="pass")
        self.opportunity = CareerOpportunity.objects.create(
            title="Review role",
            company_name="Tella Labs",
            lifecycle_status=CareerOpportunity.LifecycleStatus.PUBLISHED,
            application_mode=CareerOpportunity.ApplicationMode.INTERNAL,
        )
        self.application = OpportunityApplicationService.submit(
            opportunity=self.opportunity,
            applicant=self.learner,
            contact_phone="12345",
            cover_note="My cover note",
            resume=SimpleUploadedFile(
                "resume.pdf", b"%PDF resume", content_type="application/pdf"
            ),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_list_supports_opportunity_status_and_search_filters(self):
        response = self.client.get(
            "/api/v1/opportunity-applications/",
            {
                "opportunity": str(self.opportunity.id),
                "status": "SUBMITTED",
                "search": "candidate@",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [str(self.application.id)])
        self.assertEqual(response.data[0]["cover_note"], "My cover note")
        self.assertNotIn("storage_key", response.data[0])

    def test_review_note_and_transition_record_audit_data(self):
        note = self.client.patch(
            f"/api/v1/opportunity-applications/{self.application.id}/review_note/",
            {"review_notes": "Excellent portfolio"},
            format="json",
        )
        self.assertEqual(note.status_code, 200, note.data)
        self.assertEqual(note.data["review_notes"], "Excellent portfolio")

        transition = self.client.post(
            f"/api/v1/opportunity-applications/{self.application.id}/transition/",
            {"status": "SHORTLISTED"},
            format="json",
        )
        self.assertEqual(transition.status_code, 200, transition.data)
        self.assertEqual(transition.data["status"], "SHORTLISTED")
        self.assertEqual(transition.data["reviewed_by_email"], self.admin.email)
        self.assertIsNotNone(transition.data["reviewed_at"])

    def test_reviewer_can_download_and_unassigned_staff_is_denied(self):
        downloaded = self.client.get(
            f"/api/v1/opportunity-applications/{self.application.id}/resume/"
        )
        self.assertEqual(downloaded.status_code, 200)

        self.client.force_authenticate(self.teacher)
        denied = self.client.get(
            f"/api/v1/opportunity-applications/{self.application.id}/resume/"
        )
        self.assertEqual(denied.status_code, 403)
