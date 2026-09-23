from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.constants import GroupName
from progress.models import CareerOpportunity


User = get_user_model()


class StaffOpportunityAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)
        cls.admin = User.objects.create_user(email="opp-admin@example.com", password="pass")
        cls.admin.groups.add(Group.objects.get(name=GroupName.ADMIN))
        cls.teacher = User.objects.create_user(email="opp-teacher@example.com", password="pass")
        cls.teacher.groups.add(Group.objects.get(name=GroupName.TEACHER))

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def opportunity(self, **overrides):
        values = {
            "title": "Optimization internship",
            "company_name": "Tella Labs",
            "summary": "Build models",
            "description_markdown": "## Build models",
            "employment_type": CareerOpportunity.EmploymentType.INTERNSHIP,
            "workplace_mode": CareerOpportunity.WorkplaceMode.REMOTE,
            "remote_region": "India",
            "application_mode": CareerOpportunity.ApplicationMode.INTERNAL,
            "application_deadline": timezone.now() + timedelta(days=7),
        }
        values.update(overrides)
        return CareerOpportunity.objects.create(**values)

    def test_search_and_filters_are_combined(self):
        expected = self.opportunity()
        self.opportunity(
            title="Office analyst",
            employment_type=CareerOpportunity.EmploymentType.FULL_TIME,
            workplace_mode=CareerOpportunity.WorkplaceMode.IN_OFFICE,
            physical_location="Mumbai",
        )

        response = self.client.get(
            "/api/v1/career-opportunities/",
            {
                "search": "Tella",
                "employment_type": "INTERNSHIP",
                "workplace_mode": "REMOTE",
                "lifecycle_status": "DRAFT",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [str(expected.id)])

    def test_authorized_admin_can_publish_close_and_archive(self):
        opportunity = self.opportunity()

        published = self.client.post(
            f"/api/v1/career-opportunities/{opportunity.id}/publish/"
        )
        self.assertEqual(published.status_code, 200, published.data)
        self.assertEqual(published.data["lifecycle_status"], "PUBLISHED")

        closed = self.client.post(
            f"/api/v1/career-opportunities/{opportunity.id}/close/"
        )
        self.assertEqual(closed.status_code, 200, closed.data)

        archived = self.client.post(
            f"/api/v1/career-opportunities/{opportunity.id}/archive/"
        )
        self.assertEqual(archived.status_code, 200, archived.data)
        self.assertEqual(archived.data["lifecycle_status"], "ARCHIVED")

    def test_unauthorized_staff_cannot_use_lifecycle_action(self):
        opportunity = self.opportunity()
        self.client.force_authenticate(self.teacher)

        response = self.client.post(
            f"/api/v1/career-opportunities/{opportunity.id}/publish/"
        )

        self.assertEqual(response.status_code, 403)

    def test_incomplete_publication_returns_field_errors(self):
        opportunity = CareerOpportunity.objects.create(title="Incomplete")

        response = self.client.post(
            f"/api/v1/career-opportunities/{opportunity.id}/publish/"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("company_name", response.data)
