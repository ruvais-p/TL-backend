import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("curriculum", "0002_phase2_curriculum"), ("media_library", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="ActivityContent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content_type", models.CharField(default="application/json", max_length=80)),
                ("content", models.JSONField(blank=True, default=dict)),
                ("activity", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="content", to="curriculum.learningactivity")),
            ],
        ),
        migrations.CreateModel(
            name="Experiment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("experiment_type", models.CharField(choices=[("HTML_INTERACTIVE", "HTML interactive"), ("EMBEDDED", "Embedded"), ("SIMULATION", "Simulation"), ("QUESTION_BASED", "Question based")], max_length=30)),
                ("instructions", models.TextField()),
                ("configuration", models.JSONField(blank=True, default=dict)),
                ("external_url", models.URLField(blank=True, max_length=2048, null=True)),
                ("activity", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="experiment", to="curriculum.learningactivity")),
            ],
        ),
        migrations.CreateModel(
            name="PracticeSet",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("passing_score", models.DecimalField(decimal_places=2, default=70, max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("activity", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="practice_set", to="curriculum.learningactivity")),
            ],
            options={"ordering": ["display_order", "created_at"]},
        ),
        migrations.CreateModel(
            name="Video",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("duration_seconds", models.PositiveIntegerField()),
                ("transcript", models.TextField(blank=True)),
                ("captions", models.JSONField(blank=True, default=list)),
                ("completion_percentage", models.PositiveSmallIntegerField(default=90, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)])),
                ("activity", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="video", to="curriculum.learningactivity")),
                ("media_asset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="videos", to="media_library.mediaasset")),
                ("thumbnail", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="video_thumbnails", to="media_library.mediaasset")),
            ],
        ),
        migrations.CreateModel(
            name="PracticeItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("item_type", models.CharField(choices=[("VIDEO", "Video"), ("QUESTION", "Question"), ("PRACTICE", "Practice")], max_length=20)),
                ("question_reference", models.UUIDField(blank=True, null=True)),
                ("display_order", models.PositiveIntegerField()),
                ("is_required", models.BooleanField(default=True)),
                ("practice_set", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="content.practiceset")),
                ("video", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="practice_items", to="content.video")),
            ],
            options={"ordering": ["display_order", "created_at"]},
        ),
        migrations.AddConstraint(model_name="practiceitem", constraint=models.UniqueConstraint(fields=("practice_set", "display_order"), name="unique_practice_item_order")),
        migrations.AddConstraint(model_name="practiceitem", constraint=models.CheckConstraint(condition=models.Q(models.Q(("item_type", "VIDEO"), ("question_reference__isnull", True), ("video__isnull", False)), models.Q(("item_type", "QUESTION"), ("question_reference__isnull", False), ("video__isnull", True)), models.Q(("item_type", "PRACTICE"), ("question_reference__isnull", True), ("video__isnull", True)), _connector="OR"), name="practice_item_reference_matches_type")),
    ]
