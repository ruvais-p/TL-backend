import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="MediaAsset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("file_name", models.CharField(max_length=255)),
                ("file_type", models.CharField(db_index=True, max_length=50)),
                ("mime_type", models.CharField(max_length=120)),
                ("file_size", models.PositiveBigIntegerField(default=0)),
                ("storage_path", models.CharField(max_length=1024, unique=True)),
                ("cdn_url", models.URLField(blank=True, max_length=2048)),
                ("duration_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("status", models.CharField(choices=[("UPLOADING", "Uploading"), ("PROCESSING", "Processing"), ("READY", "Ready"), ("FAILED", "Failed"), ("ARCHIVED", "Archived")], db_index=True, default="UPLOADING", max_length=20)),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="media_assets_uploaded", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="mediaasset", index=models.Index(fields=["status", "file_type", "created_at"], name="media_status_type_created_idx")),
    ]
