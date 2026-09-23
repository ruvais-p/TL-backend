from django.db.models import TextChoices


class GroupName(TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
    ADMIN = "ADMIN", "Admin"
    ACADEMIC_MANAGER = "ACADEMIC_MANAGER", "Academic Manager"
    CONTENT_MANAGER = "CONTENT_MANAGER", "Content Manager"
    TEACHER = "TEACHER", "Teacher"
    STUDENT = "STUDENT", "Student"


PROTECTED_GROUPS = {GroupName.SUPER_ADMIN}
