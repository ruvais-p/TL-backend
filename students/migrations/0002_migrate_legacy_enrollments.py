from django.db import migrations


def migrate_legacy_enrollments(apps, schema_editor):
    LegacyEnrollment = apps.get_model("progress", "Enrollment")
    Enrollment = apps.get_model("students", "Enrollment")
    CourseVersion = apps.get_model("curriculum", "CourseVersion")

    for legacy in LegacyEnrollment.objects.select_related("course").iterator():
        version = CourseVersion.objects.filter(
            course_id=legacy.course_id, status="PUBLISHED",
        ).order_by("-version_number").first()
        if version is None:
            version = CourseVersion.objects.filter(course_id=legacy.course_id).order_by("-version_number").first()
        if version is None:
            version = CourseVersion.objects.create(
                course_id=legacy.course_id,
                version_number=1,
                name="Migrated version",
                status="PUBLISHED" if getattr(legacy.course, "status", "DRAFT") == "PUBLISHED" else "DRAFT",
            )
        Enrollment.objects.create(
            id=legacy.id,
            student_id=legacy.user_id,
            course_id=legacy.course_id,
            course_version_id=version.id,
            status="ACTIVE" if legacy.is_active else "SUSPENDED",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0001_initial"),
        ("progress", "0001_initial"),
    ]
    operations = [migrations.RunPython(migrate_legacy_enrollments, migrations.RunPython.noop)]
