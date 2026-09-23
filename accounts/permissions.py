from functools import lru_cache

from django.apps import apps
from django.contrib.auth.models import Permission
from django.db.models import Q
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .constants import GroupName


def active_permission_queryset():
    """Return permissions owned by models in the currently installed apps."""

    active_models = Q()
    for model in apps.get_models():
        active_models |= Q(
            content_type__app_label=model._meta.app_label,
            content_type__model=model._meta.model_name,
        )
    return Permission.objects.filter(active_models)


@lru_cache(maxsize=1)
def active_permission_keys() -> frozenset[str]:
    keys = set()
    for model in apps.get_models():
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        keys.update(
            f"{app_label}.{action}_{model_name}"
            for action in model._meta.default_permissions
        )
        keys.update(
            f"{app_label}.{codename}" for codename, _name in model._meta.permissions
        )
    return frozenset(keys)


def filter_active_permission_keys(permission_keys) -> list[str]:
    """Hide permissions left behind by removed Django applications."""

    return sorted(set(permission_keys).intersection(active_permission_keys()))


def user_in_group(user, group_name: str) -> bool:
    return bool(user and user.is_authenticated and user.groups.filter(name=group_name).exists())


class IsInDjangoGroup(BasePermission):
    group_name = ""

    def has_permission(self, request, view) -> bool:
        return bool(request.user.is_superuser or user_in_group(request.user, self.group_name))


class IsSuperAdmin(IsInDjangoGroup):
    group_name = GroupName.SUPER_ADMIN


class IsAdmin(IsInDjangoGroup):
    group_name = GroupName.ADMIN


class IsAcademicManager(IsInDjangoGroup):
    group_name = GroupName.ACADEMIC_MANAGER


class IsContentManager(IsInDjangoGroup):
    group_name = GroupName.CONTENT_MANAGER


class IsTeacher(IsInDjangoGroup):
    group_name = GroupName.TEACHER


class IsStudent(IsInDjangoGroup):
    group_name = GroupName.STUDENT


class HasDjangoPermission(BasePermission):
    required_permission = ""

    def has_permission(self, request, view) -> bool:
        return bool(request.user.is_authenticated and request.user.has_perm(self.required_permission))


class CanManageUsers(HasDjangoPermission):
    required_permission = "accounts.manage_users"


class CanManagePermissions(HasDjangoPermission):
    required_permission = "accounts.manage_permissions"


class HasModelPermission(BasePermission):
    """Authorize staff endpoints with the model's standard Django permissions."""

    def has_permission(self, request, view) -> bool:
        model = getattr(getattr(view, "queryset", None), "model", None)
        if model is None or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            action = "view"
        elif request.method == "POST":
            action = "add"
        elif request.method == "DELETE":
            action = "delete"
        else:
            action = "change"
        return request.user.has_perm(
            f"{model._meta.app_label}.{action}_{model._meta.model_name}"
        )
