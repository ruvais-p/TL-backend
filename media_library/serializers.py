from django.core.files.storage import default_storage
from rest_framework import serializers

from .models import MediaAsset


class MediaAssetSerializer(serializers.ModelSerializer):
    upload = serializers.FileField(write_only=True, required=False)
    public_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = (
            "id", "file_name", "file_type", "mime_type", "file_size", "storage_path",
            "cdn_url", "public_url", "duration_seconds", "uploaded_by", "created_at", "status", "upload",
        )
        read_only_fields = ("uploaded_by", "created_at", "public_url")
        extra_kwargs = {
            "file_name": {"required": False},
            "file_type": {"required": False},
            "mime_type": {"required": False},
            "file_size": {"required": False},
            "storage_path": {"required": False},
            "status": {"required": False},
        }

    def validate(self, attrs):
        if not self.instance and "upload" not in attrs:
            required = ("file_name", "file_type", "mime_type", "storage_path")
            missing = [field for field in required if not attrs.get(field)]
            if missing:
                raise serializers.ValidationError({field: "Provide this field or upload a file." for field in missing})
        return attrs

    def get_public_url(self, instance):
        if instance.cdn_url:
            return instance.cdn_url
        if not instance.storage_path:
            return ""
        try:
            url = default_storage.url(instance.storage_path)
        except (NotImplementedError, ValueError):
            return ""
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def validate_file_size(self, value):
        if value < 0:
            raise serializers.ValidationError("File size cannot be negative.")
        return value
