from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from accounts.constants import GroupName
from curriculum.models import PublishStatus
from students.models import CourseAssignment, Enrollment, StudentGroup

from .models import CourseSupportConversation

User = get_user_model()


def active_course_enrollment(*, student, course_id=None, course_version_id=None):
    queryset = Enrollment.objects.select_related("course__program", "course_version").filter(
        student=student,
        status=Enrollment.Status.ACTIVE,
        course__status=PublishStatus.PUBLISHED,
        course__program__status=PublishStatus.PUBLISHED,
        course_version__status=PublishStatus.PUBLISHED,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    if course_id is not None:
        queryset = queryset.filter(course_id=course_id)
    if course_version_id is not None:
        queryset = queryset.filter(course_version_id=course_version_id)
    return queryset.first()


def visible_support_conversations(user):
    queryset = CourseSupportConversation.objects.select_related(
        "student", "course_version__course__program", "opened_from_enrollment"
    )
    if not user or not user.is_authenticated or not user.is_active:
        return queryset.none()
    if user.has_perm("tutoring.view_all_course_support_chats"):
        return queryset
    if user.groups.filter(name=GroupName.STUDENT).exists():
        return queryset.filter(student=user)
    if not user.has_perm("tutoring.reply_to_assigned_course_support_chats"):
        return queryset.none()
    matching_assignment = CourseAssignment.objects.filter(
        course_version_id=OuterRef("course_version_id"),
        status=CourseAssignment.Status.ACTIVE,
        student_group__status=StudentGroup.Status.ACTIVE,
        student_group__teacher=user,
        student_group__memberships__student_id=OuterRef("student_id"),
    )
    return queryset.annotate(has_matching_assignment=Exists(matching_assignment)).filter(
        has_matching_assignment=True
    )


def can_read_support_conversation(*, user, conversation) -> bool:
    return visible_support_conversations(user).filter(pk=conversation.pk).exists()


def can_send_support_message(*, user, conversation) -> bool:
    if not can_read_support_conversation(user=user, conversation=conversation):
        return False
    if user.groups.filter(name=GroupName.STUDENT).exists():
        return bool(
            user.pk == conversation.student_id
            and active_course_enrollment(
                student=user,
                course_version_id=conversation.course_version_id,
            )
        )
    return bool(
        user.has_perm("tutoring.reply_to_assigned_course_support_chats")
        or user.has_perm("tutoring.view_all_course_support_chats")
    )


def can_close_support_conversation(*, user, conversation) -> bool:
    return bool(
        user.has_perm("tutoring.close_course_support_chats")
        and can_read_support_conversation(user=user, conversation=conversation)
    )


def support_recipient_user_ids(conversation) -> set:
    teacher_ids = User.objects.filter(
        is_active=True,
        teaching_student_groups__status=StudentGroup.Status.ACTIVE,
        teaching_student_groups__memberships__student_id=conversation.student_id,
        teaching_student_groups__course_assignments__course_version_id=conversation.course_version_id,
        teaching_student_groups__course_assignments__status=CourseAssignment.Status.ACTIVE,
    ).filter(
        Q(
            groups__permissions__content_type__app_label="tutoring",
            groups__permissions__codename="reply_to_assigned_course_support_chats",
        )
        | Q(
            user_permissions__content_type__app_label="tutoring",
            user_permissions__codename="reply_to_assigned_course_support_chats",
        )
    ).values_list("id", flat=True).distinct()
    global_ids = User.objects.filter(is_active=True).filter(
        Q(is_superuser=True)
        | Q(
            groups__permissions__content_type__app_label="tutoring",
            groups__permissions__codename="view_all_course_support_chats",
        )
        | Q(
            user_permissions__content_type__app_label="tutoring",
            user_permissions__codename="view_all_course_support_chats",
        )
    ).values_list("id", flat=True).distinct()
    return {conversation.student_id, *teacher_ids, *global_ids}
