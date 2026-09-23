from rest_framework import serializers

from .models import Chapter, Course, CourseVersion, LearningActivity, Program, Subtopic


class ActivityContentRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    activity = serializers.PrimaryKeyRelatedField(read_only=True)
    content_type = serializers.CharField(read_only=True)
    content = serializers.JSONField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class ActivityExperimentRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    activity = serializers.PrimaryKeyRelatedField(read_only=True)
    experiment_type = serializers.CharField(read_only=True)
    instructions = serializers.CharField(read_only=True)
    configuration = serializers.JSONField(read_only=True)
    external_url = serializers.URLField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class LearningActivitySerializer(serializers.ModelSerializer):
    content = serializers.JSONField(source="content.content", read_only=True, default=dict)
    content_record = ActivityContentRecordSerializer(source="content", read_only=True, default=None)
    experiment = ActivityExperimentRecordSerializer(read_only=True, default=None)

    class Meta:
        model = LearningActivity
        fields = (
            "id", "subtopic", "activity_type", "title", "description", "display_order",
            "is_required", "estimated_minutes", "completion_rule", "status",
            "created_by", "updated_by", "created_at", "updated_at", "content",
            "content_record", "experiment",
        )
        read_only_fields = ("created_by", "updated_by", "created_at", "updated_at")


class SubtopicSerializer(serializers.ModelSerializer):
    activities = LearningActivitySerializer(many=True, read_only=True)

    class Meta:
        model = Subtopic
        fields = (
            "id", "chapter", "title", "slug", "description", "learning_objectives",
            "estimated_minutes", "display_order", "is_required", "status",
            "created_at", "updated_at", "activities",
        )
        read_only_fields = ("created_at", "updated_at")


class ChapterSerializer(serializers.ModelSerializer):
    subtopics = SubtopicSerializer(many=True, read_only=True)

    class Meta:
        model = Chapter
        fields = (
            "id", "course_version", "title", "slug", "description", "chapter_number",
            "estimated_minutes", "is_required", "status", "display_order", "completion_rule",
            "created_at", "updated_at", "subtopics",
        )
        read_only_fields = ("created_at", "updated_at")


class CourseVersionSerializer(serializers.ModelSerializer):
    chapters = ChapterSerializer(many=True, read_only=True)

    class Meta:
        model = CourseVersion
        fields = (
            "id", "course", "version_number", "name", "status", "published_at",
            "created_by", "created_at", "updated_at", "chapters",
        )
        read_only_fields = ("published_at", "created_by", "created_at", "updated_at")


class CourseSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source="program.name", read_only=True)
    versions = CourseVersionSerializer(many=True, read_only=True)
    published_version = serializers.SerializerMethodField()
    chatbot_available = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id", "program", "program_name", "name", "code", "description", "thumbnail",
            "status", "display_order", "created_by", "updated_by", "created_at", "updated_at",
            "versions", "published_version", "chatbot_available",
        )
        read_only_fields = ("created_by", "updated_by", "created_at", "updated_at")

    def get_published_version(self, obj):
        version = next((item for item in obj.versions.all() if item.status == "PUBLISHED"), None)
        return CourseVersionSerializer(version, context=self.context).data if version else None

    def get_chatbot_available(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        from tutoring.services import chatbot_available_for

        # The course selector records this once per request, avoiding a group
        # lookup for every serialized course while remaining false by default.
        if not getattr(request.user, "_curriculum_is_student", False):
            return False
        return chatbot_available_for(student=request.user, course_id=obj.id)


class ProgramSerializer(serializers.ModelSerializer):
    courses = CourseSerializer(many=True, read_only=True)

    class Meta:
        model = Program
        fields = (
            "id", "name", "code", "description", "grade", "status", "created_by",
            "created_at", "updated_at", "courses",
        )
        read_only_fields = ("created_by", "created_at", "updated_at")


class ReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


class DuplicateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=False)
    code = serializers.SlugField(required=False)
