from rest_framework import serializers

from .experiment_definitions import ExperimentDefinitionError, validate_experiment_configuration
from .models import ActivityContent, Experiment, PracticeItem, PracticeSet, Video


class ActivityContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityContent
        fields = ("id", "activity", "content_type", "content", "created_at", "updated_at")
        read_only_fields = ("created_at", "updated_at")


class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = (
            "id", "activity", "media_asset", "thumbnail", "title", "description",
            "duration_seconds", "transcript", "captions", "completion_percentage",
            "created_at", "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


class ExperimentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experiment
        fields = (
            "id", "activity", "experiment_type", "instructions", "configuration",
            "external_url", "created_at", "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate_configuration(self, value):
        try:
            return validate_experiment_configuration(value)
        except ExperimentDefinitionError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class PracticeItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PracticeItem
        fields = (
            "id", "practice_set", "item_type", "video", "question_reference",
            "display_order", "is_required", "created_at", "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        item_type = attrs.get("item_type", getattr(self.instance, "item_type", None))
        video = attrs.get("video", getattr(self.instance, "video", None))
        question = attrs.get("question_reference", getattr(self.instance, "question_reference", None))
        valid = (
            item_type == PracticeItem.ItemType.VIDEO and video and not question
            or item_type == PracticeItem.ItemType.QUESTION and question and not video
            or item_type == PracticeItem.ItemType.PRACTICE and not video and not question
        )
        if not valid:
            raise serializers.ValidationError("Reference fields do not match item_type.")
        return attrs


class PracticeSetSerializer(serializers.ModelSerializer):
    items = PracticeItemSerializer(many=True, read_only=True)

    class Meta:
        model = PracticeSet
        fields = (
            "id", "activity", "title", "description", "passing_score", "display_order",
            "created_at", "updated_at", "items",
        )
        read_only_fields = ("created_at", "updated_at")


class ReorderPracticeItemsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
