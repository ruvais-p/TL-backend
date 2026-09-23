from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .constants import GroupName
from .models import Auth0Identity, User


class Auth0IdentityModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")

    def test_provider_identity_is_unique(self):
        Auth0Identity.objects.create(
            user=self.user,
            issuer="https://tenant.example.auth0.com/",
            subject="auth0|one",
            email_at_link_time=self.user.email,
        )
        other = User.objects.create_user(email="other@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Auth0Identity.objects.create(
                user=other,
                issuer="https://tenant.example.auth0.com/",
                subject="auth0|one",
                email_at_link_time=other.email,
            )

    def test_user_can_have_multiple_provider_identities(self):
        for subject in ("google-oauth2|one", "samlp|two"):
            Auth0Identity.objects.create(
                user=self.user,
                issuer="https://tenant.example.auth0.com/",
                subject=subject,
                email_at_link_time=self.user.email,
            )
        self.assertEqual(self.user.auth0_identities.count(), 2)


class Auth0IdentityVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("setup_groups", verbosity=0)
        cls.admin = User.objects.create_user(email="admin-auth0@example.com")
        cls.admin.groups.add(Group.objects.get(name=GroupName.ADMIN))
        cls.student = User.objects.create_user(email="student-auth0@example.com")
        cls.student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        cls.identity = Auth0Identity.objects.create(
            user=cls.student,
            issuer="https://tenant.example.auth0.com/",
            subject="auth0|student",
            email_at_link_time=cls.student.email,
        )

    def test_account_manager_can_view_safe_identity_summary(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get(reverse("accounts:managed-user-detail", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["auth0_identities"][0]["subject"], "auth0|student")
        self.assertNotIn("token", response.data["auth0_identities"][0])

    def test_student_cannot_enumerate_identity_links(self):
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get(reverse("accounts:managed-user-list"))
        self.assertEqual(response.status_code, 403)
