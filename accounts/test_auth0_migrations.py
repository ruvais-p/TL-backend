from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Auth0IdentityMigrationTests(TransactionTestCase):
    migrate_from = ("accounts", "0002_django_groups_user_fields")
    migrate_to = ("accounts", "0003_auth0identity")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.other_targets = [
            target for target in executor.loader.graph.leaf_nodes()
            if target[0] != "accounts"
        ]
        from_targets = [*self.other_targets, self.migrate_from]
        executor.migrate(from_targets)
        old_apps = executor.loader.project_state(from_targets).apps
        User = old_apps.get_model("accounts", "User")
        ExternalUserMapping = old_apps.get_model("students", "ExternalUserMapping")
        user = User.objects.create(
            email="migration-auth0@example.com",
            username="migration-auth0",
            password="preserved-password-hash",
        )
        ExternalUserMapping.objects.create(
            user_id=user.pk,
            provider="MOODLE",
            external_user_id="moodle-42",
            metadata={"source": "preserved"},
        )
        self.user_id = user.pk
        to_targets = [*self.other_targets, self.migrate_to]
        executor = MigrationExecutor(connection)
        executor.migrate(to_targets)
        self.apps = executor.loader.project_state(to_targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate([*self.other_targets, self.migrate_to])
        super().tearDown()

    def test_forward_adds_empty_identity_table_without_changing_users(self):
        User = self.apps.get_model("accounts", "User")
        Auth0Identity = self.apps.get_model("accounts", "Auth0Identity")
        user = User.objects.get(pk=self.user_id)
        self.assertEqual(user.email, "migration-auth0@example.com")
        self.assertEqual(user.password, "preserved-password-hash")
        self.assertEqual(Auth0Identity.objects.count(), 0)

    def test_reverse_removes_only_identity_rows(self):
        Auth0Identity = self.apps.get_model("accounts", "Auth0Identity")
        Auth0Identity.objects.create(
            user_id=self.user_id,
            issuer="https://tenant.example.auth0.com/",
            subject="auth0|migration",
            email_at_link_time="migration-auth0@example.com",
        )
        reverse_targets = [*self.other_targets, self.migrate_from]
        executor = MigrationExecutor(connection)
        executor.migrate(reverse_targets)
        reverse_apps = executor.loader.project_state(reverse_targets).apps
        User = reverse_apps.get_model("accounts", "User")
        ExternalUserMapping = reverse_apps.get_model("students", "ExternalUserMapping")
        self.assertTrue(User.objects.filter(pk=self.user_id, password="preserved-password-hash").exists())
        self.assertTrue(ExternalUserMapping.objects.filter(external_user_id="moodle-42").exists())
