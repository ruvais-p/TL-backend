import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils.text import slugify


def migrate_curriculum_data(apps, schema_editor):
    Program = apps.get_model("curriculum", "Program")
    Course = apps.get_model("curriculum", "Course")
    CourseVersion = apps.get_model("curriculum", "CourseVersion")
    Chapter = apps.get_model("curriculum", "Chapter")
    Subtopic = apps.get_model("curriculum", "Subtopic")
    LearningActivity = apps.get_model("curriculum", "LearningActivity")
    for model in (Program, Course, CourseVersion, LearningActivity):
        for row in model.objects.order_by():
            row.status = "PUBLISHED" if row.is_published else "DRAFT"
            row.save(update_fields=["status"])
    for version in CourseVersion.objects.order_by():
        version.name = f"Version {version.version_number}"
        version.save(update_fields=["name"])
        used = set()
        for number, chapter in enumerate(version.chapters.order_by("display_order", "created_at"), 1):
            base = slugify(chapter.title)[:90] or f"chapter-{number}"
            candidate = base
            suffix = 1
            while candidate in used:
                suffix += 1
                candidate = f"{base[:85]}-{suffix}"
            chapter.slug = candidate
            chapter.chapter_number = number
            chapter.save(update_fields=["slug", "chapter_number"])
            used.add(candidate)
            subtopic_used = set()
            for position, subtopic in enumerate(chapter.subtopics.order_by("display_order", "created_at"), 1):
                sub_base = slugify(subtopic.title)[:90] or f"subtopic-{position}"
                sub_candidate = sub_base
                sub_suffix = 1
                while sub_candidate in subtopic_used:
                    sub_suffix += 1
                    sub_candidate = f"{sub_base[:85]}-{sub_suffix}"
                subtopic.slug = sub_candidate
                subtopic.save(update_fields=["slug"])
                subtopic_used.add(sub_candidate)


class Migration(migrations.Migration):
    # PostgreSQL cannot remove the legacy columns in the same transaction that
    # updates them because deferred FK trigger events are still pending.
    atomic = False
    dependencies = [("curriculum", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.RenameField("program", "title", "name"),
        migrations.RenameField("program", "slug", "code"),
        migrations.RenameField("program", "summary", "description"),
        migrations.RenameField("course", "title", "name"),
        migrations.RenameField("course", "slug", "code"),
        migrations.RenameField("course", "summary", "description"),
        migrations.RenameField("chapter", "order", "display_order"),
        migrations.RenameField("subtopic", "order", "display_order"),
        migrations.RenameField("learningactivity", "order", "display_order"),
        migrations.AddField("program", "grade", models.CharField(blank=True, max_length=40)),
        migrations.AddField("program", "status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("APPROVED", "Approved"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=20)),
        migrations.AddField("program", "created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="programs_created", to=settings.AUTH_USER_MODEL)),
        migrations.AddField("course", "status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("APPROVED", "Approved"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=20)),
        migrations.AddField("course", "display_order", models.PositiveIntegerField(db_index=True, default=0)),
        migrations.AddField("course", "thumbnail", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="course_thumbnails", to="curriculum.mediaasset")),
        migrations.AddField("course", "created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="courses_created", to=settings.AUTH_USER_MODEL)),
        migrations.AddField("course", "updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="courses_updated", to=settings.AUTH_USER_MODEL)),
        migrations.AddField("courseversion", "name", models.CharField(blank=True, max_length=200)),
        migrations.AddField("courseversion", "status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("APPROVED", "Approved"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=20)),
        migrations.AddField("courseversion", "published_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("courseversion", "created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="course_versions_created", to=settings.AUTH_USER_MODEL)),
        migrations.AddField("chapter", "slug", models.SlugField(max_length=100, null=True)),
        migrations.AddField("chapter", "description", models.TextField(blank=True)),
        migrations.AddField("chapter", "chapter_number", models.PositiveIntegerField(null=True)),
        migrations.AddField("chapter", "estimated_minutes", models.PositiveIntegerField(default=0)),
        migrations.AddField("chapter", "is_required", models.BooleanField(default=True)),
        migrations.AddField("chapter", "status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("APPROVED", "Approved"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=20)),
        migrations.AddField("chapter", "completion_rule", models.JSONField(blank=True, default=dict)),
        migrations.AddField("subtopic", "slug", models.SlugField(max_length=100, null=True)),
        migrations.AddField("subtopic", "description", models.TextField(blank=True)),
        migrations.AddField("subtopic", "learning_objectives", models.JSONField(blank=True, default=list)),
        migrations.AddField("subtopic", "estimated_minutes", models.PositiveIntegerField(default=0)),
        migrations.AddField("subtopic", "is_required", models.BooleanField(default=True)),
        migrations.AddField("subtopic", "status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("APPROVED", "Approved"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=20)),
        migrations.AddField("learningactivity", "description", models.TextField(blank=True)),
        migrations.AddField("learningactivity", "is_required", models.BooleanField(default=True)),
        migrations.AddField("learningactivity", "estimated_minutes", models.PositiveIntegerField(default=0)),
        migrations.AddField("learningactivity", "completion_rule", models.JSONField(blank=True, default=dict)),
        migrations.AddField("learningactivity", "status", models.CharField(choices=[("DRAFT", "Draft"), ("IN_REVIEW", "In review"), ("APPROVED", "Approved"), ("PUBLISHED", "Published"), ("ARCHIVED", "Archived")], db_index=True, default="DRAFT", max_length=20)),
        migrations.AddField("learningactivity", "created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activities_created", to=settings.AUTH_USER_MODEL)),
        migrations.AddField("learningactivity", "updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activities_updated", to=settings.AUTH_USER_MODEL)),
        migrations.RunPython(migrate_curriculum_data, migrations.RunPython.noop),
        migrations.RemoveField("program", "is_published"),
        migrations.RemoveField("course", "is_published"),
        migrations.RemoveField("courseversion", "is_published"),
        migrations.RemoveField("courseversion", "changelog"),
        migrations.RemoveField("learningactivity", "is_published"),
        migrations.AlterField("program", "code", models.SlugField(max_length=80, unique=True)),
        migrations.AlterField("course", "code", models.SlugField(max_length=80, unique=True)),
        migrations.AlterField("course", "program", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="courses", to="curriculum.program")),
        migrations.AlterField("courseversion", "course", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="curriculum.course")),
        migrations.AlterField("courseversion", "version_number", models.PositiveIntegerField()),
        migrations.AlterField("courseversion", "name", models.CharField(max_length=200)),
        migrations.AlterField("chapter", "course_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="chapters", to="curriculum.courseversion")),
        migrations.AlterField("chapter", "slug", models.SlugField(max_length=100)),
        migrations.AlterField("chapter", "chapter_number", models.PositiveIntegerField()),
        migrations.AlterField("chapter", "display_order", models.PositiveIntegerField(db_index=True, default=0)),
        migrations.AlterField("subtopic", "chapter", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subtopics", to="curriculum.chapter")),
        migrations.AlterField("subtopic", "slug", models.SlugField(max_length=100)),
        migrations.AlterField("subtopic", "display_order", models.PositiveIntegerField(db_index=True, default=0)),
        migrations.AlterField("learningactivity", "subtopic", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="activities", to="curriculum.subtopic")),
        migrations.AlterField("learningactivity", "display_order", models.PositiveIntegerField(db_index=True, default=0)),
        migrations.AlterField("learningactivity", "activity_type", models.CharField(choices=[("CONCEPT_VIDEO", "Concept video"), ("EXPERIMENT", "Experiment"), ("CONCEPT_OVERVIEW", "Concept overview"), ("OBSERVE_LEARN_PRACTICE", "Observe, learn, practice"), ("HOMEWORK", "Homework"), ("INTERACTIVE_WORKSHOP", "Interactive workshop"), ("SIMULATION", "Simulation"), ("READING", "Reading"), ("PDF", "PDF"), ("INTERACTIVE", "Interactive"), ("ASSIGNMENT", "Assignment"), ("PROJECT", "Project"), ("LIVE_CLASS", "Live class"), ("FLASHCARD", "Flashcard")], max_length=40)),
        migrations.AlterUniqueTogether("course", unique_together=set()),
        migrations.AlterUniqueTogether("courseversion", unique_together=set()),
        migrations.AlterModelOptions("program", options={"ordering": ["name"]}),
        migrations.AlterModelOptions("course", options={"ordering": ["display_order", "name"], "permissions": [("publish_course", "Can publish courses"), ("archive_course", "Can archive courses"), ("duplicate_course", "Can duplicate courses"), ("assign_course", "Can assign courses")]}),
        migrations.AlterModelOptions("courseversion", options={"ordering": ["-version_number"]}),
        migrations.AlterModelOptions("chapter", options={"ordering": ["display_order", "chapter_number", "title"], "permissions": [("publish_chapter", "Can publish chapters"), ("duplicate_chapter", "Can duplicate chapters")]}),
        migrations.AlterModelOptions("subtopic", options={"ordering": ["display_order", "title"]}),
        migrations.AlterModelOptions("learningactivity", options={"ordering": ["display_order", "title"], "verbose_name_plural": "learning activities"}),
        migrations.AddConstraint("courseversion", models.UniqueConstraint(fields=("course", "version_number"), name="unique_course_version_number")),
        migrations.AddConstraint("chapter", models.UniqueConstraint(fields=("course_version", "slug"), name="unique_chapter_slug_per_version")),
        migrations.AddConstraint("chapter", models.UniqueConstraint(fields=("course_version", "chapter_number"), name="unique_chapter_number_per_version")),
        migrations.AddConstraint("subtopic", models.UniqueConstraint(fields=("chapter", "slug"), name="unique_subtopic_slug_per_chapter")),
        migrations.AddConstraint("learningactivity", models.UniqueConstraint(fields=("subtopic", "display_order"), name="unique_activity_order_per_subtopic")),
        migrations.AddIndex("program", models.Index(fields=["status", "created_at"], name="program_status_created_idx")),
        migrations.AddIndex("course", models.Index(fields=["program", "status", "display_order"], name="course_prog_status_ord_idx")),
        migrations.AddIndex("courseversion", models.Index(fields=["course", "status", "version_number"], name="version_course_status_num_idx")),
        migrations.AddIndex("chapter", models.Index(fields=["course_version", "status", "display_order"], name="chapter_ver_status_ord_idx")),
        migrations.AddIndex("subtopic", models.Index(fields=["chapter", "status", "display_order"], name="subtopic_ch_status_ord_idx")),
        migrations.AddIndex("learningactivity", models.Index(fields=["subtopic", "status", "display_order"], name="activity_sub_status_ord_idx")),
    ]
