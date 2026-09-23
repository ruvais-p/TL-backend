from dataclasses import dataclass

from .constants import GroupName


STAFF_GROUPS = frozenset({
    GroupName.SUPER_ADMIN,
    GroupName.ADMIN,
    GroupName.ACADEMIC_MANAGER,
    GroupName.CONTENT_MANAGER,
    GroupName.TEACHER,
})
PORTALS = frozenset({"staff", "learner"})


@dataclass(frozen=True)
class AdmissionResult:
    allowed: bool
    reason: str


def portal_admission(user, portal: str) -> AdmissionResult:
    if portal not in PORTALS:
        return AdmissionResult(False, "invalid_portal")
    if not user or not user.is_active:
        return AdmissionResult(False, "inactive")
    group_names = set(user.groups.values_list("name", flat=True))
    if portal == "learner":
        allowed = GroupName.STUDENT in group_names
        return AdmissionResult(allowed, "allowed" if allowed else "wrong_portal")
    allowed = user.is_superuser or bool(group_names.intersection(STAFF_GROUPS))
    return AdmissionResult(allowed, "allowed" if allowed else "wrong_portal")
