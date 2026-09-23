from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Auth0Identity, User
from .permissions import active_permission_queryset, filter_active_permission_keys
from .services import create_managed_user, update_managed_user
from .admission import PORTALS, portal_admission


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    groups = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    portal_access = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "username", "first_name", "last_name", "display_name",
            "is_active", "is_superuser", "date_joined", "groups", "permissions",
            "portal_access",
        )
        read_only_fields = ("is_superuser",)

    def get_groups(self, obj) -> list[str]:
        return list(obj.groups.order_by("name").values_list("name", flat=True))

    def get_permissions(self, obj) -> list[str]:
        return filter_active_permission_keys(obj.get_all_permissions())

    def get_portal_access(self, obj) -> dict[str, bool]:
        return {
            "staff": portal_admission(obj, "staff").allowed,
            "learner": portal_admission(obj, "learner").allowed,
        }


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.USERNAME_FIELD
    portal = serializers.ChoiceField(choices=sorted(PORTALS), required=False, write_only=True)

    def validate(self, attrs):
        portal = attrs.pop("portal", None)
        result = super().validate(attrs)
        if portal and not portal_admission(self.user, portal).allowed:
            raise PermissionDenied("This account cannot access the requested workspace.")
        return result

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["groups"] = list(user.groups.values_list("name", flat=True))
        token["auth_method"] = "password"
        return token


class Auth0ExchangeSerializer(serializers.Serializer):
    assertion = serializers.CharField(write_only=True, trim_whitespace=False)
    portal = serializers.ChoiceField(choices=sorted(PORTALS))


class Auth0IdentitySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Auth0Identity
        fields = (
            "id", "issuer", "subject", "email_at_link_time",
            "created_at", "last_authenticated_at",
        )
        read_only_fields = fields


class ManagedUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    groups = serializers.SlugRelatedField(
        many=True,
        slug_field="name",
        queryset=Group.objects.order_by("name"),
        required=False,
    )
    display_name = serializers.CharField(read_only=True)
    permissions = serializers.SerializerMethodField()
    auth0_identities = Auth0IdentitySummarySerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "email", "username", "first_name", "last_name", "display_name",
            "password", "is_active", "date_joined", "groups", "permissions",
            "auth0_identities",
        )
        read_only_fields = ("id", "date_joined", "display_name", "permissions")

    def validate_password(self, value):
        candidate = User(
            email=self.initial_data.get("email", getattr(self.instance, "email", "")),
            username=self.initial_data.get("username", getattr(self.instance, "username", "")),
            first_name=self.initial_data.get("first_name", getattr(self.instance, "first_name", "")),
            last_name=self.initial_data.get("last_name", getattr(self.instance, "last_name", "")),
        )
        try:
            validate_password(value, candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "A password is required."})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        groups = validated_data.pop("groups", [])
        password = validated_data.pop("password")
        return create_managed_user(
            actor=request.user,
            password=password,
            groups=groups,
            **validated_data,
        )

    def update(self, instance, validated_data):
        request = self.context["request"]
        groups = validated_data.pop("groups", None)
        password = validated_data.pop("password", None)
        return update_managed_user(
            actor=request.user,
            user=instance,
            password=password,
            groups=groups,
            **validated_data,
        )

    def get_permissions(self, obj) -> list[str]:
        return filter_active_permission_keys(obj.get_all_permissions())


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Group
        fields = ("id", "name", "user_count", "permissions")

    def get_permissions(self, obj) -> list[str]:
        return filter_active_permission_keys(
            f"{permission.content_type.app_label}.{permission.codename}"
            for permission in obj.permissions.all()
        )


class RolePermissionsSerializer(serializers.Serializer):
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=True)

    def validate_permissions(self, values):
        available = {
            f"{permission.content_type.app_label}.{permission.codename}": permission
            for permission in active_permission_queryset().select_related("content_type")
        }
        missing = sorted(set(values) - available.keys())
        if missing:
            raise serializers.ValidationError(f"Unknown permissions: {', '.join(missing)}")
        self.context["resolved_permissions"] = [available[value] for value in dict.fromkeys(values)]
        return values


class PermissionSerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField()
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)

    class Meta:
        model = Permission
        fields = ("id", "key", "name", "app_label", "codename")

    def get_key(self, obj) -> str:
        return f"{obj.content_type.app_label}.{obj.codename}"
