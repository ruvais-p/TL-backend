from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.constants import GroupName


User = get_user_model()


class OpportunityPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)

    def user_in(self, group_name, email):
        user = User.objects.create_user(email=email, password="StrongPass123!")
        user.groups.add(Group.objects.get(name=group_name))
        return user

    def test_administrator_receives_management_and_review_permissions(self):
        administrator = self.user_in(GroupName.ADMIN, "opportunity-admin@example.com")

        self.assertTrue(administrator.has_perm("progress.view_careeropportunity"))
        self.assertTrue(administrator.has_perm("progress.add_careeropportunity"))
        self.assertTrue(administrator.has_perm("progress.change_careeropportunity"))
        self.assertTrue(administrator.has_perm("progress.view_opportunityapplication"))
        self.assertTrue(administrator.has_perm("progress.change_opportunityapplication"))
        self.assertTrue(
            administrator.has_perm("progress.review_opportunityapplication")
        )
        self.assertTrue(
            administrator.has_perm(
                "progress.download_opportunityapplicationdocument"
            )
        )

    def test_super_administrator_retains_all_opportunity_permissions(self):
        super_admin = self.user_in(
            GroupName.SUPER_ADMIN, "opportunity-super-admin@example.com"
        )

        self.assertTrue(super_admin.has_perm("progress.add_careeropportunity"))
        self.assertTrue(super_admin.has_perm("progress.delete_careeropportunity"))
        self.assertTrue(super_admin.has_perm("progress.review_opportunityapplication"))

    def test_unassigned_staff_role_cannot_read_staff_opportunity_api(self):
        teacher = self.user_in(GroupName.TEACHER, "opportunity-teacher@example.com")
        client = APIClient()
        client.force_authenticate(teacher)

        response = client.get("/api/v1/career-opportunities/")

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_create_through_staff_api(self):
        administrator = self.user_in(GroupName.ADMIN, "creator@example.com")
        client = APIClient()
        client.force_authenticate(administrator)

        response = client.post(
            "/api/v1/career-opportunities/",
            {"title": "Draft opportunity"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
