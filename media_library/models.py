import uuid

from django.conf import settings
from django.db import models


class MediaAsset(models.Model):
    class Status(models.TextChoices):
        UPLOADING = "UPLOADING", "Uploading"
        PROCESSING = "PROCESSING", "Processing"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50, db_index=True)
    mime_type = models.CharField(max_length=120)
    file_size = models.PositiveBigIntegerField(default=0)
    storage_path = models.CharField(max_length=1024, unique=True)
    cdn_url = models.URLField(max_length=2048, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="media_assets_uploaded",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADING, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "file_type", "created_at"], name="media_status_type_created_idx")]

    def __str__(self) -> str:
        return self.file_name
