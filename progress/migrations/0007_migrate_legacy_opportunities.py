from django.db import migrations


EMPLOYMENT_TYPE_MAP = {
    "intern": "INTERNSHIP",
    "internship": "INTERNSHIP",
    "full_time": "FULL_TIME",
    "full-time": "FULL_TIME",
    "full time": "FULL_TIME",
    "part_time": "PART_TIME",
    "part-time": "PART_TIME",
    "part time": "PART_TIME",
    "contract": "CONTRACT",
    "contractor": "CONTRACT",
    "apprentice": "APPRENTICESHIP",
    "apprenticeship": "APPRENTICESHIP",
    "project": "PROJECT",
    "earn_while_learn": "PROJECT",
}


def forwards(apps, schema_editor):
    CareerOpportunity = apps.get_model("progress", "CareerOpportunity")
    for opportunity in CareerOpportunity.objects.all().iterator():
        normalized_kind = (opportunity.kind or "").strip().lower()
        opportunity.legacy_kind = opportunity.kind or ""
        opportunity.employment_type = EMPLOYMENT_TYPE_MAP.get(
            normalized_kind, "PROJECT"
        )
        opportunity.lifecycle_status = (
            "PUBLISHED" if opportunity.is_published else "DRAFT"
        )
        if opportunity.summary and not opportunity.description_markdown:
            opportunity.description_markdown = opportunity.summary
        if opportunity.url:
            opportunity.application_mode = "EXTERNAL"
            opportunity.application_url = opportunity.url
        else:
            opportunity.application_mode = "INTERNAL"
        opportunity.save(
            update_fields=[
                "legacy_kind",
                "employment_type",
                "lifecycle_status",
                "description_markdown",
                "application_mode",
                "application_url",
            ]
        )


def backwards(apps, schema_editor):
    CareerOpportunity = apps.get_model("progress", "CareerOpportunity")
    for opportunity in CareerOpportunity.objects.all().iterator():
        if opportunity.legacy_kind:
            opportunity.kind = opportunity.legacy_kind
        if opportunity.description_markdown and not opportunity.summary:
            opportunity.summary = opportunity.description_markdown
        if opportunity.application_url and not opportunity.url:
            opportunity.url = opportunity.application_url
        opportunity.is_published = opportunity.lifecycle_status == "PUBLISHED"
        opportunity.save(update_fields=["kind", "summary", "url", "is_published"])


class Migration(migrations.Migration):
    dependencies = [("progress", "0006_structured_opportunities")]

    operations = [migrations.RunPython(forwards, backwards)]
