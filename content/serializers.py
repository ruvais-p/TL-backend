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

    MAX_CAPTION_CUES = 2000
    MAX_CAPTION_TEXT = 500

    def validate_captions(self, value):
        """Captions are timed cues: [{"start": seconds, "end": seconds, "text": "..."}], in order."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Captions must be a list of cues.")
        if len(value) > self.MAX_CAPTION_CUES:
            raise serializers.ValidationError(f"Use at most {self.MAX_CAPTION_CUES} caption cues.")
        cues = []
        previous_start = 0.0
        for index, cue in enumerate(value, start=1):
            if not isinstance(cue, dict):
                raise serializers.ValidationError(f"Cue {index} must be an object with start, end and text.")
            start, end, text = cue.get("start"), cue.get("end"), cue.get("text")
            if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                raise serializers.ValidationError(f"Cue {index} needs numeric start and end times in seconds.")
            if start < 0 or end <= start:
                raise serializers.ValidationError(f"Cue {index} must end after it starts.")
            if start < previous_start:
                raise serializers.ValidationError(f"Cue {index} starts before the previous cue; keep cues in time order.")
            if not isinstance(text, str) or not text.strip():
                raise serializers.ValidationError(f"Cue {index} needs caption text.")
            if len(text) > self.MAX_CAPTION_TEXT:
                raise serializers.ValidationError(f"Cue {index} is longer than {self.MAX_CAPTION_TEXT} characters.")
            previous_start = float(start)
            cues.append({"start": round(float(start), 3), "end": round(float(end), 3), "text": text.strip()})
        return cues


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
