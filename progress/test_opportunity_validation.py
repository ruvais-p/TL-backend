from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from media_library.models import MediaAsset
from progress.models import CareerOpportunity
from progress.serializers import StaffCareerOpportunitySerializer


class OpportunityValidationTests(TestCase):
    def valid_payload(self, **overrides):
        payload = {
            "title": "Optimization internship",
            "company_name": "Tella Labs",
            "summary": "Apply modelling skills in a real team.",
            "description_markdown": "## What you will do\n\nBuild useful models.",
            "employment_type": "INTERNSHIP",
            "workplace_mode": "REMOTE",
            "remote_region": "India",
            "lifecycle_status": "PUBLISHED",
            "application_mode": "INTERNAL",
            "compensation_disclosure": "PAID",
            "compensation_currency": "INR",
            "compensation_min": "20000.00",
            "compensation_max": "30000.00",
            "compensation_pay_period": "MONTH",
            "application_deadline": (timezone.now() + timedelta(days=14)).isoformat(),
        }
        payload.update(overrides)
        return payload

    def assert_field_error(self, field, **overrides):
        serializer = StaffCareerOpportunitySerializer(data=self.valid_payload(**overrides))
        self.assertFalse(serializer.is_valid())
        self.assertIn(field, serializer.errors)

    def test_valid_published_opportunity(self):
        serializer = StaffCareerOpportunitySerializer(data=self.valid_payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_employment_and_workplace_enums_are_independent(self):
        self.assert_field_error("employment_type", employment_type="REMOTE")
        self.assert_field_error("workplace_mode", workplace_mode="INTERNSHIP")

    def test_conditional_location_is_required_for_publication(self):
        self.assert_field_error(
            "physical_location", workplace_mode="HYBRID", remote_region=""
        )

    def test_paid_compensation_requires_valid_range_currency_and_period(self):
        self.assert_field_error("compensation_max", compensation_max="10000.00")
        self.assert_field_error("compensation_currency", compensation_currency="XXX")
        self.assert_field_error("compensation_pay_period", compensation_pay_period="")

    def test_external_application_must_use_https(self):
        self.assert_field_error(
            "application_url",
            application_mode="EXTERNAL",
            application_url="http://example.com/apply",
        )

    def test_publication_rejects_past_deadline(self):
        self.assert_field_error(
            "application_deadline",
            application_deadline=(timezone.now() - timedelta(minutes=1)).isoformat(),
        )

    def test_company_logo_must_be_a_ready_image(self):
        document = MediaAsset.objects.create(
            file_name="brief.pdf",
            file_type="DOCUMENT",
            mime_type="application/pdf",
            file_size=100,
            storage_path="logos/brief.pdf",
            status=MediaAsset.Status.READY,
        )
        self.assert_field_error("company_logo", company_logo=str(document.id))

    def test_incomplete_draft_can_be_saved(self):
        serializer = StaffCareerOpportunitySerializer(data={"title": "Early draft"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
