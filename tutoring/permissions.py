from rest_framework.permissions import BasePermission


class CanManageCourseChatbot(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user.is_authenticated and request.user.has_perm("tutoring.manage_course_chatbot"))

