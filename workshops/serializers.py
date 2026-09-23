from rest_framework import serializers

from .math import validate_config
from .models import WorkshopConfig, WorkshopModel


class WorkshopModelSerializer(serializers.ModelSerializer):
    validation = serializers.SerializerMethodField()

    class Meta:
        model = WorkshopModel
        fields = (
            "id",
            "activity",
            "user",
            "name",
            "config",
            "validation",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at", "validation")

    def get_validation(self, obj):
        return validate_config(obj.config or {})

    def validate_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Config must be an object.")
        result = validate_config(value)
        if result.get("errors"):
            raise serializers.ValidationError(result["errors"])
        return value


class WorkshopConfigSerializer(serializers.ModelSerializer):
    activity_title = serializers.CharField(source="activity.title", read_only=True)

    class Meta:
        model = WorkshopConfig
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "activity_title")

    def validate(self, attrs):
        def value(name):
            return attrs.get(name, getattr(self.instance, name, None))

        result = validate_config(
            {
                "price1": value("price1"),
                "priceDrop1": value("price_drop1"),
                "cost1": value("cost1"),
                "price2": value("price2"),
                "priceDrop2": value("price_drop2"),
                "cost2": value("cost2"),
                "congestion": value("congestion"),
                "fixedCost": value("fixed_cost"),
            }
        )
        if result.get("errors"):
            field_names = {
                "priceDrop1": "price_drop1",
                "priceDrop2": "price_drop2",
                "fixedCost": "fixed_cost",
            }
            raise serializers.ValidationError(
                {
                    field_names.get(key, key): message
                    for key, message in result["errors"].items()
                }
            )
        return attrs


class StaffWorkshopModelSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    activity_title = serializers.CharField(source="activity.title", read_only=True)

    class Meta:
        model = WorkshopModel
        fields = tuple(field.name for field in WorkshopModel._meta.fields) + (
            "user_email",
            "activity_title",
        )
        read_only_fields = fields
