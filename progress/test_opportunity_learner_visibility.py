from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from progress.models import CareerOpportunity, OpportunityApplication
from students.models import StudentGroup, StudentGroupMember


User = get_user_model()


class LearnerOpportunityVisibilityTests(TestCase):
    def setUp(self):
        self.learner = User.objects.create_user(email="visible@example.com", password="pass")
        self.other = User.objects.create_user(email="outside@example.com", password="pass")
        self.group = StudentGroup.objects.create(
            name="Grade 10", code="grade-10", grade="10", academic_year=2026
        )
        StudentGroupMember.objects.create(student_group=self.group, student=self.learner)
        self.client = APIClient()

    def opportunity(self, **overrides):
        values = {
            "title": "Open role",
            "company_name": "Tella Labs",
            "lifecycle_status": CareerOpportunity.LifecycleStatus.PUBLISHED,
            "is_published": True,
            "application_deadline": timezone.now() + timedelta(days=3),
        }
        values.update(overrides)
        return CareerOpportunity.objects.create(**values)

    def test_catalog_contains_only_open_audience_visible_records(self):
        all_learners = self.opportunity(title="All learners")
        selected = self.opportunity(
            title="Selected group",
            audience_scope=CareerOpportunity.AudienceScope.SELECTED_GROUPS,
        )
        selected.audience_groups.add(self.group)
        self.opportunity(
            title="Expired", application_deadline=timezone.now() - timedelta(seconds=1)
        )
        self.opportunity(title="Draft", lifecycle_status=CareerOpportunity.LifecycleStatus.DRAFT)
        self.client.force_authenticate(self.learner)

        response = self.client.get("/api/v1/career/opportunities/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row["id"] for row in response.data},
            {str(all_learners.id), str(selected.id)},
        )

    def test_outside_audience_cannot_list_or_retrieve_record(self):
        selected = self.opportunity(
            audience_scope=CareerOpportunity.AudienceScope.SELECTED_GROUPS
        )
        selected.audience_groups.add(self.group)
        self.client.force_authenticate(self.other)

        collection = self.client.get("/api/v1/career/opportunities/")
        detail = self.client.get(f"/api/v1/career/opportunities/{selected.id}/")

        self.assertEqual(collection.data, [])
        self.assertEqual(detail.status_code, 404)

    def test_existing_applicant_retains_closed_detail_access(self):
        closed = self.opportunity(
            lifecycle_status=CareerOpportunity.LifecycleStatus.CLOSED,
            is_published=False,
        )
        OpportunityApplication.objects.create(
            opportunity=closed,
            applicant=self.learner,
            applicant_name="Visible Learner",
            applicant_email=self.learner.email,
            contact_phone="+91 90000 00000",
        )
        self.client.force_authenticate(self.learner)

        collection = self.client.get("/api/v1/career/opportunities/")
        detail = self.client.get(f"/api/v1/career/opportunities/{closed.id}/")

        self.assertEqual(collection.data, [])
        self.assertEqual(detail.status_code, 200)

    def test_visible_ineligible_learner_receives_reasons_without_rule_config(self):
        opportunity = self.opportunity(
            eligibility_rules={
                "version": 1,
                "match": "ALL",
                "conditions": [
                    {"fact": "GROUP_GRADE", "operator": "IN", "values": ["12"]}
                ],
            }
        )
        self.client.force_authenticate(self.learner)

        response = self.client.get(f"/api/v1/career/opportunities/{opportunity.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["eligibility"]["eligible"])
        self.assertTrue(response.data["eligibility"]["reasons"])
        self.assertNotIn("eligibility_rules", response.data)
        self.assertNotIn("audience_groups", response.data)

    def test_catalog_query_count_is_constant_for_multiple_opportunities(self):
        self.opportunity(title="First")
        self.opportunity(title="Second")
        self.client.force_authenticate(self.learner)

        with self.assertNumQueries(5):
            response = self.client.get("/api/v1/career/opportunities/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
