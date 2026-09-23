from rest_framework.permissions import SAFE_METHODS, BasePermission


class CanManageCurriculum(BasePermission):
    action_permissions = {
        "reorder_chapters": "curriculum.change_chapter",
        "reorder_subtopics": "curriculum.change_subtopic",
        "reorder_activities": "curriculum.change_learningactivity",
    }

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return request.user.has_perm("curriculum.view_course")
        if permission := self.action_permissions.get(getattr(view, "action", "")):
            return request.user.has_perm(permission)
        model = getattr(getattr(view, "queryset", None), "model", None)
        if model is None:
            return False
        action = "add" if request.method == "POST" else "change"
        return request.user.has_perm(f"{model._meta.app_label}.{action}_{model._meta.model_name}")


class CanPublishCurriculum(BasePermission):
    def has_permission(self, request, view) -> bool:
        return request.user.has_perm("curriculum.publish_course")
