from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .constants import GroupName, PROTECTED_GROUPS


@transaction.atomic
def assign_group(*, actor, user, group: Group) -> None:
    if not actor.has_perm("accounts.manage_users"):
        raise PermissionDenied("You cannot manage user groups.")
    if group.name in PROTECTED_GROUPS and not actor.has_perm("accounts.manage_permissions"):
        raise PermissionDenied("Only permission administrators can assign SUPER_ADMIN.")
    if user == actor and group.name == GroupName.SUPER_ADMIN and not actor.is_superuser:
        raise PermissionDenied("Self-escalation is not permitted.")
    user.groups.add(group)


def _require_user_management(actor, permission: str) -> None:
    if not actor.has_perm("accounts.manage_users") or not actor.has_perm(permission):
        raise PermissionDenied("You cannot manage users.")


def _validate_group_change(*, actor, user, groups) -> None:
    current_names = set(user.groups.values_list("name", flat=True)) if user.pk else set()
    requested_names = {group.name for group in groups}
    protected_changes = (current_names ^ requested_names) & PROTECTED_GROUPS
    if protected_changes and not actor.has_perm("accounts.manage_permissions"):
        raise PermissionDenied("Only permission administrators can change SUPER_ADMIN membership.")
    if (
        user == actor
        and GroupName.SUPER_ADMIN in requested_names - current_names
        and not actor.is_superuser
    ):
        raise PermissionDenied("Self-escalation is not permitted.")


@transaction.atomic
def create_managed_user(*, actor, password: str, groups=(), **data):
    from .models import User

    _require_user_management(actor, "accounts.add_user")
    user = User.objects.create_user(password=password, **data)
    requested_groups = list(groups)
    _validate_group_change(actor=actor, user=user, groups=requested_groups)
    user.groups.set(requested_groups)
    return user


@transaction.atomic
def update_managed_user(*, actor, user, password: str | None = None, groups=None, **data):
    _require_user_management(actor, "accounts.change_user")
    if (
        user.groups.filter(name__in=PROTECTED_GROUPS).exists()
        and not actor.has_perm("accounts.manage_permissions")
    ):
        raise PermissionDenied("Only permission administrators can update SUPER_ADMIN accounts.")
    if groups is not None:
        requested_groups = list(groups)
        _validate_group_change(actor=actor, user=user, groups=requested_groups)
    for field, value in data.items():
        setattr(user, field, value)
    if password:
        user.set_password(password)
    user.save()
    if groups is not None:
        user.groups.set(requested_groups)
    return user
