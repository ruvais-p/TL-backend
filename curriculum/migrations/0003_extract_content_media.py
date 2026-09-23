import os
import django.db.models.deletion
from django.db import migrations, models


def copy_legacy_rows(apps, schema_editor):
    LegacyMedia = apps.get_model("curriculum", "MediaAsset")
    MediaAsset = apps.get_model("media_library", "MediaAsset")
    LegacyContent = apps.get_model("curriculum", "ActivityContent")
    ActivityContent = apps.get_model("content", "ActivityContent")
    for row in LegacyMedia.objects.order_by():
        path = str(row.file or f"legacy/{row.id}")
        file_name = os.path.basename(path) or row.title
        extension = os.path.splitext(file_name)[1].lstrip(".").upper() or "FILE"
        MediaAsset.objects.update_or_create(
            id=row.id,
            defaults={
                "file_name": file_name[:255], "file_type": extension[:50],
                "mime_type": row.mime_type or "application/octet-stream", "file_size": 0,
                "storage_path": path, "status": "READY", "uploaded_by_id": row.uploaded_by_id,
            },
        )
    for row in LegacyContent.objects.order_by():
        ActivityContent.objects.update_or_create(
            id=row.id,
            defaults={"activity_id": row.activity_id, "content_type": "application/json", "content": row.payload},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0002_phase2_curriculum"),
        ("content", "0001_initial"),
        ("media_library", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(copy_legacy_rows, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="course", name="thumbnail",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="course_thumbnails", to="media_library.mediaasset"),
        ),
        migrations.DeleteModel(name="ActivityContent"),
        migrations.DeleteModel(name="MediaAsset"),
    ]
