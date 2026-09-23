from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.constants import GroupName


class AssessmentPermission(BasePermission):
    def has_permission(self, request, view):
        if getattr(view, "action", None) in {"start", "submit", "results"}:
            return request.user.is_authenticated
        model = getattr(getattr(view, "queryset", None), "model", None)
        if model is None:
            return False
        if request.method in SAFE_METHODS:
            return request.user.has_perm(f"assessments.view_{model._meta.model_name}")
        action = "add" if request.method == "POST" else "change"
        return request.user.has_perm(f"assessments.{action}_{model._meta.model_name}")
