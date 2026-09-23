from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LegacyOpportunityMigrationTests(TransactionTestCase):
    migrate_from = ("progress", "0005_alter_courseprogress_options")
    migrate_to = ("progress", "0007_migrate_legacy_opportunities")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.other_targets = [
            target
            for target in executor.loader.graph.leaf_nodes()
            if target[0] != "progress"
        ]
        from_targets = [*self.other_targets, self.migrate_from]
        executor.migrate(from_targets)
        old_apps = executor.loader.project_state(from_targets).apps
        LegacyUser = old_apps.get_model("accounts", "User")
        LegacyOpportunity = old_apps.get_model("progress", "CareerOpportunity")
        user = LegacyUser.objects.create(
            email="migration-learner@example.com",
            password="unusable",
        )
        published = LegacyOpportunity.objects.create(
            title="Legacy internship",
            kind="internship",
            summary="A preserved summary",
            url="https://example.com/apply",
            is_published=True,
        )
        LegacyOpportunity.objects.create(
            title="Ambiguous draft",
            kind="graduate_rotation",
            summary="Review this mapping",
            is_published=False,
        )
        self.user_id = user.id
        self.published_id = published.id
        self.executor = MigrationExecutor(connection)
        to_targets = [*self.other_targets, self.migrate_to]
        self.executor.migrate(to_targets)
        self.apps = self.executor.loader.project_state(to_targets).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(
            [*self.other_targets, ("progress", "0007_migrate_legacy_opportunities")]
        )
        super().tearDown()

    def test_forward_mapping_preserves_published_external_opportunity(self):
        Opportunity = self.apps.get_model("progress", "CareerOpportunity")
        migrated = Opportunity.objects.get(title="Legacy internship")

        self.assertEqual(migrated.legacy_kind, "internship")
        self.assertEqual(migrated.employment_type, "INTERNSHIP")
        self.assertEqual(migrated.lifecycle_status, "PUBLISHED")
        self.assertEqual(migrated.description_markdown, "A preserved summary")
        self.assertEqual(migrated.application_mode, "EXTERNAL")
        self.assertEqual(migrated.application_url, "https://example.com/apply")

    def test_ambiguous_kind_is_conservative_and_reviewable(self):
        Opportunity = self.apps.get_model("progress", "CareerOpportunity")
        migrated = Opportunity.objects.get(title="Ambiguous draft")

        self.assertEqual(migrated.legacy_kind, "graduate_rotation")
        self.assertEqual(migrated.employment_type, "PROJECT")
        self.assertEqual(migrated.lifecycle_status, "DRAFT")
        self.assertFalse(migrated.is_published)

    def test_reverse_preserves_opportunities_and_application_records(self):
        Application = self.apps.get_model("progress", "OpportunityApplication")
        application = Application.objects.create(
            opportunity_id=self.published_id,
            applicant_id=self.user_id,
            applicant_name="Migration Learner",
            applicant_email="migration-learner@example.com",
            contact_phone="9876543210",
            cover_note="Preserve this application",
            status="SHORTLISTED",
            review_notes="Strong candidate",
        )

        executor = MigrationExecutor(connection)
        reverse_targets = [
            *self.other_targets,
            ("progress", "0006_structured_opportunities"),
        ]
        executor.migrate(reverse_targets)
        reverse_apps = executor.loader.project_state(
            reverse_targets
        ).apps
        Opportunity = reverse_apps.get_model("progress", "CareerOpportunity")
        ReversedApplication = reverse_apps.get_model(
            "progress", "OpportunityApplication"
        )

        opportunity = Opportunity.objects.get(id=self.published_id)
        preserved_application = ReversedApplication.objects.get(id=application.id)
        self.assertEqual(Opportunity.objects.count(), 2)
        self.assertEqual(opportunity.kind, "internship")
        self.assertEqual(opportunity.summary, "A preserved summary")
        self.assertEqual(opportunity.url, "https://example.com/apply")
        self.assertTrue(opportunity.is_published)
        self.assertEqual(opportunity.application_url, "https://example.com/apply")
        self.assertEqual(preserved_application.status, "SHORTLISTED")
        self.assertEqual(
            preserved_application.cover_note, "Preserve this application"
        )
        self.assertEqual(preserved_application.review_notes, "Strong candidate")
