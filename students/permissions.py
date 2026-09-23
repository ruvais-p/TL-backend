from rest_framework.permissions import SAFE_METHODS, BasePermission


class CanAccessStudentDomain(BasePermission):
    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return request.user.has_perm("accounts.view_user")
        return request.user.has_perm("students.manage_students") or request.user.has_perm("students.manage_student_groups")
