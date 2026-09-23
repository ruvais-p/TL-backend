from rest_framework.permissions import SAFE_METHODS, BasePermission


class CanManageContent(BasePermission):
    def has_permission(self, request, view) -> bool:
        model = getattr(getattr(view, "queryset", None), "model", None)
        if model is None:
            return False
        action = "view" if request.method in SAFE_METHODS else ("add" if request.method == "POST" else "change")
        return request.user.has_perm(f"content.{action}_{model._meta.model_name}")
