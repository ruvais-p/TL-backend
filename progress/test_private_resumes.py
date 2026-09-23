import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from accounts.constants import GroupName
from progress.application_services import ApplicationSubmissionError, OpportunityApplicationService
from progress.models import CareerOpportunity, OpportunityApplicationDocument
from progress.private_documents import ResumeAccessError, open_resume


User = get_user_model()


class PrivateResumeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings_override = self.settings(PRIVATE_DOCUMENT_ROOT=self.temporary.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.learner = User.objects.create_user(email="resume-owner@example.com", password="pass")
        self.reviewer = User.objects.create_user(email="resume-reviewer@example.com", password="pass")
        self.reviewer.groups.add(Group.objects.get(name=GroupName.ADMIN))
        self.outsider = User.objects.create_user(email="resume-outsider@example.com", password="pass")
        self.opportunity = CareerOpportunity.objects.create(
            title="Resume role",
            lifecycle_status=CareerOpportunity.LifecycleStatus.PUBLISHED,
            application_mode=CareerOpportunity.ApplicationMode.INTERNAL,
            resume_required=True,
        )

    def upload(self, content=b"%PDF-1.4 resume", content_type="application/pdf", name="resume.pdf"):
        return SimpleUploadedFile(name, content, content_type=content_type)

    def submit(self, upload):
        return OpportunityApplicationService.submit(
            opportunity=self.opportunity,
            applicant=self.learner,
            contact_phone="123",
            resume=upload,
        )

    def test_valid_resume_uses_private_non_guessable_storage_and_metadata(self):
        application = self.submit(self.upload(name="../Asha Resume.pdf"))
        document = application.resume_document

        self.assertRegex(document.storage_key, r"^applications/[0-9a-f]{32}$")
        self.assertEqual(document.original_filename, "Asha Resume.pdf")
        self.assertEqual(len(document.checksum_sha256), 64)
        self.assertTrue(Path(self.temporary.name, document.storage_key).exists())
        self.assertFalse(hasattr(document, "url"))

    def test_applicant_and_authorized_reviewer_can_open_resume(self):
        document = self.submit(self.upload()).resume_document
        with open_resume(document=document, user=self.learner) as stream:
            self.assertEqual(stream.read(), b"%PDF-1.4 resume")
        with open_resume(document=document, user=self.reviewer) as stream:
            self.assertEqual(stream.read(), b"%PDF-1.4 resume")

    def test_unauthorized_access_uses_non_disclosing_error(self):
        document = self.submit(self.upload()).resume_document
        with self.assertRaisesRegex(ResumeAccessError, "Resume not found"):
            open_resume(document=document, user=self.outsider)

    def test_invalid_mime_and_oversized_file_create_nothing(self):
        for upload in (
            self.upload(content_type="text/plain", name="resume.txt"),
            self.upload(content=b"x" * (5 * 1024 * 1024 + 1)),
        ):
            with self.assertRaises(ApplicationSubmissionError):
                self.submit(upload)
            self.assertEqual(OpportunityApplicationDocument.objects.count(), 0)
            self.assertEqual(list(Path(self.temporary.name).rglob("*")), [])
