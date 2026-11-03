from decimal import Decimal

from django.db import migrations


def clamp_scores(apps, schema_editor):
    """Cap chapter learning-check scores recorded from inflated attempts (see assessments 0002)."""
    apps.get_model("progress", "ChapterProgress").objects.filter(learning_check_score__gt=100).update(learning_check_score=Decimal("100"))


class Migration(migrations.Migration):
    dependencies = [("progress", "0008_normalize_activity_status")]

    operations = [migrations.RunPython(clamp_scores, migrations.RunPython.noop)]
