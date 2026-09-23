import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from curriculum.models import LearningActivity
from media_library.models import MediaAsset


class TimestampedUUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActivityContent(TimestampedUUIDModel):
    activity = models.OneToOneField(LearningActivity, on_delete=models.CASCADE, related_name="content")
    content_type = models.CharField(max_length=80, default="application/json")
    content = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"Content for {self.activity.title}"


class Video(TimestampedUUIDModel):
    activity = models.OneToOneField(LearningActivity, on_delete=models.PROTECT, related_name="video")
    media_asset = models.ForeignKey(MediaAsset, on_delete=models.PROTECT, related_name="videos")
    thumbnail = models.ForeignKey(
        MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name="video_thumbnails"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField()
    transcript = models.TextField(blank=True)
    captions = models.JSONField(default=list, blank=True)
    completion_percentage = models.PositiveSmallIntegerField(
        default=90, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )

    def __str__(self) -> str:
        return self.title


class Experiment(TimestampedUUIDModel):
    class ExperimentType(models.TextChoices):
        HTML_INTERACTIVE = "HTML_INTERACTIVE", "HTML interactive"
        EMBEDDED = "EMBEDDED", "Embedded"
        SIMULATION = "SIMULATION", "Simulation"
        QUESTION_BASED = "QUESTION_BASED", "Question based"

    activity = models.OneToOneField(LearningActivity, on_delete=models.PROTECT, related_name="experiment")
    experiment_type = models.CharField(max_length=30, choices=ExperimentType.choices)
    instructions = models.TextField()
    configuration = models.JSONField(default=dict, blank=True)
    external_url = models.URLField(max_length=2048, null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.activity.title}: {self.get_experiment_type_display()}"


class PracticeSet(TimestampedUUIDModel):
    activity = models.OneToOneField(LearningActivity, on_delete=models.PROTECT, related_name="practice_set")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    passing_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=70,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "created_at"]

    def __str__(self) -> str:
        return self.title


class PracticeItem(TimestampedUUIDModel):
    class ItemType(models.TextChoices):
        VIDEO = "VIDEO", "Video"
        QUESTION = "QUESTION", "Question"
        PRACTICE = "PRACTICE", "Practice"

    practice_set = models.ForeignKey(PracticeSet, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    video = models.ForeignKey(Video, on_delete=models.PROTECT, null=True, blank=True, related_name="practice_items")
    question_reference = models.UUIDField(null=True, blank=True)
    display_order = models.PositiveIntegerField()
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["practice_set", "display_order"], name="unique_practice_item_order"),
            models.CheckConstraint(
                condition=(
                    models.Q(item_type="VIDEO", video__isnull=False, question_reference__isnull=True)
                    | models.Q(item_type="QUESTION", video__isnull=True, question_reference__isnull=False)
                    | models.Q(item_type="PRACTICE", video__isnull=True, question_reference__isnull=True)
                ),
                name="practice_item_reference_matches_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.practice_set}: {self.display_order}"
