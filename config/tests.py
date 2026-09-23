from django.conf import settings
from django.core.checks import run_checks
from django.test import SimpleTestCase


class BackendSurfaceTests(SimpleTestCase):
    def test_django_is_api_only(self):
        self.assertNotIn("portal", settings.INSTALLED_APPS)
        self.assertNotIn("django.contrib.admin", settings.INSTALLED_APPS)
        self.assertNotIn("django.contrib.sessions", settings.INSTALLED_APPS)
        self.assertNotIn("django.contrib.messages", settings.INSTALLED_APPS)
        self.assertNotIn("django.contrib.staticfiles", settings.INSTALLED_APPS)
        self.assertEqual(settings.TEMPLATES, [])
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"],
            ("rest_framework.renderers.JSONRenderer",),
        )
        self.assertEqual(self.client.get("/manage/").status_code, 404)
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_health_endpoint_remains_available(self):
        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_auth0_is_disabled_by_default(self):
        self.assertFalse(settings.AUTH0_ENABLED)

    def test_development_uses_an_in_memory_channel_layer(self):
        self.assertEqual(
            settings.CHANNEL_LAYERS["default"]["BACKEND"],
            "channels.layers.InMemoryChannelLayer",
        )

    def test_complete_auth0_configuration_passes_security_checks(self):
        with self.settings(
            AUTH0_ENABLED=True,
            AUTH0_ISSUER="https://tenant.example.auth0.com/",
            AUTH0_AUDIENCE="https://api.example.org",
            AUTH0_ALGORITHM="RS256",
            AUTH0_EMAIL_CLAIM="https://tella.systems/email",
            AUTH0_EMAIL_VERIFIED_CLAIM="https://tella.systems/email_verified",
            AUTH0_JWKS_CACHE_SECONDS=300,
            AUTH0_HTTP_TIMEOUT_SECONDS=5,
        ):
            self.assertFalse([error for error in run_checks(tags=["security"]) if error.id.startswith("accounts.")])

    def test_incomplete_enabled_auth0_configuration_fails_checks(self):
        with self.settings(
            AUTH0_ENABLED=True,
            AUTH0_ISSUER="",
            AUTH0_AUDIENCE="",
            AUTH0_ALGORITHM="HS256",
            AUTH0_EMAIL_CLAIM="",
            AUTH0_EMAIL_VERIFIED_CLAIM="",
            AUTH0_JWKS_CACHE_SECONDS=0,
            AUTH0_HTTP_TIMEOUT_SECONDS=0,
        ):
            ids = {error.id for error in run_checks(tags=["security"])}
        self.assertTrue({"accounts.E001", "accounts.E002", "accounts.E003"}.issubset(ids))

    def test_auth0_issuer_must_be_an_https_origin(self):
        with self.settings(
            AUTH0_ENABLED=True,
            AUTH0_ISSUER="http://tenant.example.auth0.com/path/",
            AUTH0_AUDIENCE="https://api.example.org",
            AUTH0_ALGORITHM="RS256",
            AUTH0_EMAIL_CLAIM="https://tella.systems/email",
            AUTH0_EMAIL_VERIFIED_CLAIM="https://tella.systems/email_verified",
            AUTH0_JWKS_CACHE_SECONDS=300,
            AUTH0_HTTP_TIMEOUT_SECONDS=5,
        ):
            ids = {error.id for error in run_checks(tags=["security"])}
        self.assertIn("accounts.E004", ids)
