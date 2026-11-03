from decimal import Decimal

from django.db import migrations
from django.db.models import F, Q


def clamp_scores(apps, schema_editor):
    """Repair attempts graded before duplicate answers were rejected (score above max_score)."""
    Attempt = apps.get_model("assessments", "AssessmentAttempt")
    for attempt in Attempt.objects.filter(Q(score__gt=F("max_score")) | Q(percentage__gt=100)).select_related("learning_check"):
        attempt.score = min(attempt.score or Decimal("0"), attempt.max_score)
        attempt.percentage = (attempt.score * 100 / attempt.max_score).quantize(Decimal("0.01")) if attempt.max_score else Decimal("0")
        attempt.passed = attempt.percentage >= attempt.learning_check.passing_score
        attempt.save(update_fields=["score", "percentage", "passed"])


class Migration(migrations.Migration):
    dependencies = [("assessments", "0001_initial")]

    operations = [migrations.RunPython(clamp_scores, migrations.RunPython.noop)]
