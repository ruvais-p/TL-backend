from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import CourseAssignment, Enrollment, ExternalUserMapping, StudentGroup, StudentGroupMember

User = get_user_model()


class StudentGroupMemberSerializer(serializers.ModelSerializer):
    student_detail = UserSerializer(source="student", read_only=True)

    class Meta:
        model = StudentGroupMember
        fields = ("id", "student_group", "student", "student_detail", "joined_at")
        read_only_fields = ("joined_at",)


class StudentGroupSerializer(serializers.ModelSerializer):
    memberships = StudentGroupMemberSerializer(many=True, read_only=True)
    teacher_detail = UserSerializer(source="teacher", read_only=True)
    member_count = serializers.IntegerField(source="memberships.count", read_only=True)

    class Meta:
        model = StudentGroup
        fields = ("id", "name", "code", "grade", "academic_year", "teacher", "teacher_detail", "status", "created_at", "updated_at", "member_count", "memberships")
        read_only_fields = ("created_at", "updated_at")


class EnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = (
            "id", "student", "course", "course_version", "status", "enrolled_at",
            "started_at", "completed_at", "expires_at", "created_at", "updated_at",
        )
        read_only_fields = ("enrolled_at", "created_at", "updated_at")


class CourseAssignmentSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source="course.name", read_only=True)
    course_version_name = serializers.CharField(source="course_version.name", read_only=True)
    assigned_by_detail = UserSerializer(source="assigned_by", read_only=True)
    enrollment_outcome = serializers.SerializerMethodField()
    class Meta:
        model = CourseAssignment
        fields = (
            "id", "course", "course_version", "student_group", "student", "assigned_by",
            "course_name", "course_version_name", "assigned_by_detail", "assigned_at", "due_date", "status", "created_at", "updated_at", "enrollment_outcome",
        )
        read_only_fields = ("assigned_by", "assigned_at", "created_at", "updated_at")

    def get_enrollment_outcome(self, obj):
        return getattr(obj, "enrollment_outcome", None)

    def validate(self, attrs):
        if (attrs.get("student_group") is None) == (attrs.get("student") is None):
            raise serializers.ValidationError("Exactly one of student_group or student is required.")
        return attrs


class ExternalUserMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalUserMapping
        fields = ("id", "user", "provider", "external_user_id", "metadata", "created_at")
        read_only_fields = ("created_at",)
