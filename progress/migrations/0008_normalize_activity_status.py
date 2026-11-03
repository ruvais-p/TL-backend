from django.db import migrations
from django.db.models.functions import Upper

CANONICAL = ("NOT_STARTED", "IN_PROGRESS", "COMPLETED")


def normalize(apps, schema_editor):
    ActivityProgress = apps.get_model("progress", "ActivityProgress")
    ActivityProgress.objects.update(status=Upper("status"))
    ActivityProgress.objects.filter(progress_percentage__gte=100).update(status="COMPLETED")
    ActivityProgress.objects.exclude(status__in=CANONICAL).update(status="IN_PROGRESS")


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0007_migrate_legacy_opportunities"),
    ]

    operations = [
        migrations.RunPython(normalize, migrations.RunPython.noop),
    ]
