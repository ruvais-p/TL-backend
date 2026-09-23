from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.constants import GroupName

from .models import CourseAssignment, Enrollment, ExternalUserMapping, StudentGroup, StudentGroupMember

User = get_user_model()


def is_teacher(user) -> bool:
    return user.groups.filter(name=GroupName.TEACHER).exists() and not user.is_superuser


def is_student(user) -> bool:
    return user.groups.filter(name=GroupName.STUDENT).exists() and not user.is_superuser


def visible_student_groups(user):
    queryset = StudentGroup.objects.select_related("teacher").prefetch_related("memberships__student")
    if is_teacher(user):
        return queryset.filter(teacher=user)
    if is_student(user):
        return queryset.filter(memberships__student=user)
    return queryset


def visible_students(user):
    queryset = User.objects.filter(groups__name=GroupName.STUDENT).distinct().prefetch_related("groups")
    if is_teacher(user):
        return queryset.filter(student_group_memberships__student_group__teacher=user).distinct()
    if is_student(user):
        return queryset.filter(pk=user.pk)
    return queryset


def visible_memberships(user):
    queryset = StudentGroupMember.objects.select_related("student", "student_group", "student_group__teacher")
    if is_teacher(user):
        return queryset.filter(student_group__teacher=user)
    if is_student(user):
        return queryset.filter(student=user)
    return queryset


def visible_enrollments(user):
    queryset = Enrollment.objects.select_related("student", "course", "course_version")
    if is_teacher(user):
        return queryset.filter(student__student_group_memberships__student_group__teacher=user).distinct()
    if is_student(user):
        return queryset.filter(student=user)
    return queryset


def visible_assignments(user):
    queryset = CourseAssignment.objects.select_related("course", "course_version", "student_group", "student", "assigned_by")
    if is_teacher(user):
        return queryset.filter(Q(student_group__teacher=user) | Q(student__student_group_memberships__student_group__teacher=user)).distinct()
    if is_student(user):
        return queryset.filter(Q(student=user) | Q(student_group__memberships__student=user)).distinct()
    return queryset


def visible_external_mappings(user):
    queryset = ExternalUserMapping.objects.select_related("user")
    return queryset.filter(user=user) if is_student(user) else queryset
