from rest_framework.permissions import SAFE_METHODS, BasePermission


class CanManageMedia(BasePermission):
    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return request.user.has_perm("media_library.view_mediaasset")
        action = "add" if request.method == "POST" else "change"
        return request.user.has_perm(f"media_library.{action}_mediaasset")
