import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_django_groups_user_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Auth0Identity",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("issuer", models.URLField(max_length=500)),
                ("subject", models.CharField(max_length=255)),
                ("email_at_link_time", models.EmailField(max_length=254)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_authenticated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auth0_identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["issuer", "subject"],
                "indexes": [models.Index(fields=["user", "issuer"], name="auth0_identity_user_issuer_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("issuer", "subject"),
                        name="unique_auth0_issuer_subject",
                    )
                ],
            },
        ),
    ]
