from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
import hashlib
import hmac
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import close_old_connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from jwt import PyJWKClientError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .admission import portal_admission
from .auth0 import (
    Auth0AdmissionError,
    Auth0Claims,
    Auth0VerificationError,
    exchange_auth0_assertion,
    resolve_auth0_identity,
    verify_auth0_assertion,
)
from .constants import GroupName
from .managers import normalize_email_address
from .models import Auth0Identity, User

AUTH0_SETTINGS = {
    "AUTH0_ENABLED": True,
    "AUTH0_ISSUER": "https://tenant.example.auth0.com/",
    "AUTH0_AUDIENCE": "https://api.example.org",
    "AUTH0_ALGORITHM": "RS256",
    "AUTH0_EMAIL_CLAIM": "https://tella.systems/email",
    "AUTH0_EMAIL_VERIFIED_CLAIM": "https://tella.systems/email_verified",
    "AUTH0_JWKS_CACHE_SECONDS": 300,
    "AUTH0_HTTP_TIMEOUT_SECONDS": 1,
}


class StaticSigningKey:
    def __init__(self, key):
        self.key = key


class StaticJwksClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return StaticSigningKey(self.key)


@override_settings(**AUTH0_SETTINGS)
class Auth0AssertionVerifierTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwks = StaticJwksClient(cls.private_key.public_key())

    def assertion(self, **overrides):
        now = timezone.now()
        payload = {
            "iss": AUTH0_SETTINGS["AUTH0_ISSUER"],
            "aud": AUTH0_SETTINGS["AUTH0_AUDIENCE"],
            "sub": "auth0|learner",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            AUTH0_SETTINGS["AUTH0_EMAIL_CLAIM"]: " Learner@Example.COM ",
            AUTH0_SETTINGS["AUTH0_EMAIL_VERIFIED_CLAIM"]: True,
        }
        payload.update(overrides)
        return jwt.encode(payload, self.private_key, algorithm="RS256", headers={"kid": "test-key"})

    def reason_for(self, assertion, client=None):
        with self.assertRaises(Auth0VerificationError) as caught:
            verify_auth0_assertion(assertion, jwks_client=client or self.jwks)
        return caught.exception.reason

    def test_valid_assertion_returns_canonical_claims(self):
        claims = verify_auth0_assertion(self.assertion(), jwks_client=self.jwks)
        self.assertEqual(claims.subject, "auth0|learner")
        self.assertEqual(claims.email, "learner@example.com")
        self.assertTrue(claims.email_verified)

    def test_rejects_wrong_issuer_audience_and_expiry(self):
        self.assertEqual(self.reason_for(self.assertion(iss="https://wrong.example/")), "wrong_issuer")
        self.assertEqual(self.reason_for(self.assertion(aud="wrong-audience")), "wrong_audience")
        self.assertEqual(
            self.reason_for(self.assertion(exp=timezone.now() - timedelta(seconds=1))),
            "expired",
        )

    def test_rejects_unsupported_algorithm_before_key_lookup(self):
        token = jwt.encode({"sub": "auth0|learner"}, "not-a-real-secret-but-long-enough", algorithm="HS256")
        self.assertEqual(self.reason_for(token), "unsupported_algorithm")

    def test_rejects_missing_required_claims(self):
        self.assertEqual(self.reason_for(self.assertion(sub=None)), "invalid_assertion")
        self.assertEqual(
            self.reason_for(self.assertion(**{AUTH0_SETTINGS["AUTH0_EMAIL_CLAIM"]: None})),
            "missing_email",
        )
        self.assertEqual(
            self.reason_for(self.assertion(**{AUTH0_SETTINGS["AUTH0_EMAIL_VERIFIED_CLAIM"]: "true"})),
            "missing_email_verification",
        )

    def test_rejects_unknown_key_or_jwks_failure(self):
        class BrokenClient:
            def get_signing_key_from_jwt(self, token):
                raise PyJWKClientError("key unavailable")

        self.assertEqual(self.reason_for(self.assertion(), BrokenClient()), "invalid_assertion")

    def test_jwks_client_refreshes_once_for_a_rotated_key(self):
        old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode(
            {
                "iss": AUTH0_SETTINGS["AUTH0_ISSUER"],
                "aud": AUTH0_SETTINGS["AUTH0_AUDIENCE"],
                "sub": "auth0|rotated",
                "iat": timezone.now(),
                "exp": timezone.now() + timedelta(minutes=5),
                AUTH0_SETTINGS["AUTH0_EMAIL_CLAIM"]: "rotated@example.com",
                AUTH0_SETTINGS["AUTH0_EMAIL_VERIFIED_CLAIM"]: True,
            },
            new_key,
            algorithm="RS256",
            headers={"kid": "new-key"},
        )

        def jwk(key, kid):
            value = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
            value.update({"kid": kid, "use": "sig", "alg": "RS256"})
            return value

        client = jwt.PyJWKClient("https://tenant.example.auth0.com/.well-known/jwks.json")
        with patch.object(
            client,
            "fetch_data",
            side_effect=[{"keys": [jwk(old_key, "old-key")]}, {"keys": [jwk(new_key, "new-key")]}],
        ) as fetch:
            claims = verify_auth0_assertion(token, jwks_client=client)
        self.assertEqual(claims.subject, "auth0|rotated")
        self.assertEqual(fetch.call_count, 2)

    @override_settings(AUTH0_ENABLED=False)
    def test_rejects_exchange_when_auth0_is_disabled(self):
        self.assertEqual(self.reason_for(self.assertion()), "disabled")


class EmailNormalizationTests(SimpleTestCase):
    def test_normalizes_whitespace_and_case(self):
        self.assertEqual(normalize_email_address("  Student@Example.COM "), "student@example.com")


class PortalAdmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)

    def user_in(self, group_name, **kwargs):
        user = User.objects.create_user(email=f"{group_name.lower()}-{User.objects.count()}@example.com", **kwargs)
        user.groups.add(Group.objects.get(name=group_name))
        return user

    def test_staff_groups_are_admitted(self):
        for group_name in (
            GroupName.SUPER_ADMIN,
            GroupName.ADMIN,
            GroupName.ACADEMIC_MANAGER,
            GroupName.CONTENT_MANAGER,
            GroupName.TEACHER,
        ):
            self.assertTrue(portal_admission(self.user_in(group_name), "staff").allowed)

    def test_superuser_is_admitted_to_staff(self):
        user = User.objects.create_superuser(email="super-auth0@example.com")
        self.assertTrue(portal_admission(user, "staff").allowed)

    def test_student_and_teacher_are_admitted_only_to_their_portals(self):
        student = self.user_in(GroupName.STUDENT)
        teacher = self.user_in(GroupName.TEACHER)
        self.assertTrue(portal_admission(student, "learner").allowed)
        self.assertFalse(portal_admission(student, "staff").allowed)
        self.assertTrue(portal_admission(teacher, "staff").allowed)
        self.assertFalse(portal_admission(teacher, "learner").allowed)

    def test_inactive_user_is_denied(self):
        student = self.user_in(GroupName.STUDENT, is_active=False)
        self.assertFalse(portal_admission(student, "learner").allowed)


@override_settings(**AUTH0_SETTINGS)
class Auth0IdentityResolutionTests(TestCase):
    def claims(self, **overrides):
        values = {
            "issuer": AUTH0_SETTINGS["AUTH0_ISSUER"],
            "subject": "auth0|learner",
            "email": "learner@example.com",
            "email_verified": True,
        }
        values.update(overrides)
        return Auth0Claims(**values)

    def test_first_link_uses_verified_normalized_email(self):
        user = User.objects.create_user(email="Learner@Example.COM")
        resolved = resolve_auth0_identity(self.claims(email=" LEARNER@example.com "), correlation_id="correlation")
        self.assertEqual(resolved, user)
        identity = Auth0Identity.objects.get()
        self.assertEqual(identity.user, user)
        self.assertEqual(identity.email_at_link_time, "learner@example.com")
        self.assertIsNotNone(identity.last_authenticated_at)

    def test_existing_link_wins_when_provider_email_changes(self):
        user = User.objects.create_user(email="learner@example.com")
        Auth0Identity.objects.create(
            user=user,
            issuer=AUTH0_SETTINGS["AUTH0_ISSUER"],
            subject="auth0|learner",
            email_at_link_time=user.email,
        )
        User.objects.create_user(email="changed@example.com")
        resolved = resolve_auth0_identity(self.claims(email="changed@example.com"))
        self.assertEqual(resolved, user)
        self.assertEqual(Auth0Identity.objects.get().email_at_link_time, "learner@example.com")

    def test_unknown_unverified_and_inactive_users_are_denied(self):
        with self.assertRaises(Auth0AdmissionError) as unknown:
            resolve_auth0_identity(self.claims())
        self.assertEqual(unknown.exception.reason, "unknown_email")

        User.objects.create_user(email="learner@example.com")
        with self.assertRaises(Auth0AdmissionError) as unverified:
            resolve_auth0_identity(self.claims(email_verified=False))
        self.assertEqual(unverified.exception.reason, "unverified_email")

        User.objects.filter(email="learner@example.com").update(is_active=False)
        with self.assertRaises(Auth0AdmissionError) as inactive:
            resolve_auth0_identity(self.claims())
        self.assertEqual(inactive.exception.reason, "inactive")

    def test_ambiguous_legacy_case_variants_are_denied(self):
        User(email="learner@example.com", username="one", password="!").save(force_insert=True)
        User(email="LEARNER@example.com", username="two", password="!").save(force_insert=True)
        with self.assertRaises(Auth0AdmissionError) as caught:
            resolve_auth0_identity(self.claims())
        self.assertEqual(caught.exception.reason, "ambiguous_email")

    def test_preprovisioned_user_with_unusable_password_can_link(self):
        call_command("setup_groups", verbosity=0)
        user = User.objects.create_user(email="learner@example.com", password=None)
        user.groups.add(Group.objects.get(name=GroupName.STUDENT))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(resolve_auth0_identity(self.claims()), user)
        self.assertFalse(user.check_password("anything"))

    def test_security_logs_do_not_include_assertion_or_profile_data(self):
        User.objects.create_user(email="learner@example.com")
        assertion = "provider-secret-token"
        with patch("accounts.auth0.verify_auth0_assertion", return_value=self.claims()):
            with self.assertLogs("accounts.auth0", level="INFO") as captured:
                exchange_auth0_assertion(assertion, correlation_id="request-123")
        output = " ".join(captured.output)
        self.assertIn("request-123", output)
        self.assertNotIn(assertion, output)
        self.assertNotIn("learner@example.com", output)


@override_settings(**AUTH0_SETTINGS)
class Auth0ConcurrentLinkTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_first_login_has_one_canonical_link(self):
        user = User.objects.create_user(email="concurrent@example.com")
        claims = Auth0Claims(
            issuer=AUTH0_SETTINGS["AUTH0_ISSUER"],
            subject="auth0|concurrent",
            email=user.email,
            email_verified=True,
        )

        def resolve():
            close_old_connections()
            try:
                return resolve_auth0_identity(claims).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: resolve(), range(2)))
        self.assertEqual(results, [user.pk, user.pk])
        self.assertEqual(Auth0Identity.objects.count(), 1)


@override_settings(**AUTH0_SETTINGS)
class Auth0ExchangeApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)
        cls.student = User.objects.create_user(email="api-student@example.com", password=None)
        cls.student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        cls.admin = User.objects.create_user(email="api-admin@example.com")
        cls.admin.groups.add(Group.objects.get(name=GroupName.ADMIN))

    def setUp(self):
        self.client = APIClient()

    def exchange(self, user, portal):
        with patch("accounts.views.exchange_auth0_assertion", return_value=user):
            return self.client.post(
                reverse("accounts:auth0-exchange"),
                {"assertion": "signed-provider-assertion", "portal": portal},
                format="json",
            )

    def test_staff_and_learner_exchange_issue_auth0_platform_tokens(self):
        for user, portal in ((self.admin, "staff"), (self.student, "learner")):
            response = self.exchange(user, portal)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["user"]["id"], str(user.pk))
            self.assertEqual(RefreshToken(response.data["refresh"])["auth_method"], "auth0")

    def test_wrong_portal_and_identity_denials_are_generic(self):
        wrong_portal = self.exchange(self.student, "staff")
        with patch("accounts.views.exchange_auth0_assertion", side_effect=Auth0AdmissionError("unknown_email")):
            unknown = self.client.post(
                reverse("accounts:auth0-exchange"),
                {"assertion": "signed-provider-assertion", "portal": "staff"},
                format="json",
            )
        self.assertEqual(wrong_portal.status_code, 403)
        self.assertEqual(unknown.status_code, 403)
        self.assertEqual(wrong_portal.data, unknown.data)

    def test_auto_portal_admits_staff_and_learners(self):
        for user in (self.admin, self.student):
            response = self.exchange(user, "auto")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertIn("access", response.data)
            self.assertIn("refresh", response.data)

    def test_invalid_assertion_is_rejected_without_tokens(self):
        with patch("accounts.views.exchange_auth0_assertion", side_effect=Auth0VerificationError("expired")):
            response = self.client.post(
                reverse("accounts:auth0-exchange"),
                {"assertion": "expired-provider-assertion", "portal": "learner"},
                format="json",
            )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_local_login_can_apply_same_optional_portal_gate(self):
        self.admin.set_password("StrongPass123!")
        self.admin.save(update_fields=["password"])
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.admin.email, "password": "StrongPass123!", "portal": "staff"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(RefreshToken(response.data["refresh"])["auth_method"], "password")
        denied = self.client.post(
            reverse("accounts:login"),
            {"email": self.admin.email, "password": "StrongPass123!", "portal": "learner"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_moodle_token_uses_moodle_authentication_method(self):
        from .views import token_pair_for_user

        tokens = token_pair_for_user(self.student, "moodle")
        self.assertEqual(RefreshToken(tokens["refresh"])["auth_method"], "moodle")

    @override_settings(MOODLE_SSO_SECRET="moodle-test-secret")
    def test_existing_moodle_exchange_issues_moodle_platform_token(self):
        timestamp = int(time.time())
        email = "moodle-auth0@example.com"
        payload = f"moodle-77|{email}|{timestamp}"
        signature = hmac.new(
            b"moodle-test-secret", payload.encode(), hashlib.sha256
        ).hexdigest()
        response = self.client.post(
            reverse("accounts:moodle-exchange"),
            {
                "moodle_user_id": "moodle-77",
                "email": email,
                "timestamp": timestamp,
                "signature": signature,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(RefreshToken(response.data["refresh"])["auth_method"], "moodle")
