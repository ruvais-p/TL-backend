from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from accounts.constants import GroupName

from .models import CourseAssignment, Enrollment, ExternalUserMapping, StudentGroup, StudentGroupMember


def _require(actor, permission):
    if not actor.has_perm(permission):
        raise PermissionDenied(f"Missing permission: {permission}")


def _require_group(user, group_name, message):
    if not user.groups.filter(name=group_name).exists():
        raise ValidationError(message)


def create_student_group(*, actor, **data):
    _require(actor, "students.manage_student_groups")
    teacher = data.get("teacher")
    if teacher:
        _require_group(teacher, GroupName.TEACHER, "Assigned teacher must belong to the TEACHER Django Group.")
    return StudentGroup.objects.create(**data)


@transaction.atomic
def add_student_to_group(*, actor, student_group, student):
    _require(actor, "students.manage_student_groups")
    _require_group(student, GroupName.STUDENT, "Group members must belong to the STUDENT Django Group.")
    existing = StudentGroupMember.objects.select_for_update().filter(student_group=student_group, student=student).first()
    if existing:
        return existing
    assignments = list(CourseAssignment.objects.select_for_update().filter(
        student_group=student_group, status=CourseAssignment.Status.ACTIVE,
    ).select_related("course", "course_version"))
    for assignment in assignments:
        current = Enrollment.objects.select_for_update().filter(
            student=student, course=assignment.course, status=Enrollment.Status.ACTIVE,
        ).first()
        if current and current.course_version_id != assignment.course_version_id:
            raise ValidationError(
                f"Student has an active enrollment in another version of {assignment.course.name}."
            )
        if current is None:
            Enrollment.objects.create(
                student=student, course=assignment.course, course_version=assignment.course_version,
                status=Enrollment.Status.ACTIVE,
            )
    membership, _ = StudentGroupMember.objects.get_or_create(student_group=student_group, student=student)
    return membership


@transaction.atomic
def create_enrollment(*, actor, student, course, course_version, status=Enrollment.Status.ACTIVE, **data):
    _require(actor, "students.manage_students")
    _require_group(student, GroupName.STUDENT, "Enrollment user must belong to the STUDENT Django Group.")
    if course_version.course_id != course.id:
        raise ValidationError("CourseVersion does not belong to Course.")
    return Enrollment.objects.create(student=student, course=course, course_version=course_version, status=status, **data)


@transaction.atomic
def create_course_assignment(*, actor, course, course_version, student_group=None, student=None, **data):
    _require(actor, "students.assign_course")
    if (student_group is None) == (student is None):
        raise ValidationError("Exactly one of student_group or student is required.")
    if course_version.course_id != course.id:
        raise ValidationError("CourseVersion does not belong to Course.")
    assignment = CourseAssignment.objects.create(
        course=course, course_version=course_version, student_group=student_group,
        student=student, assigned_by=actor, **data,
    )
    student_ids = [student.pk] if student else list(
        StudentGroupMember.objects.select_for_update().filter(student_group=student_group).values_list("student_id", flat=True)
    )
    created_count = 0
    existing_count = 0
    for student_id in student_ids:
        current = Enrollment.objects.select_for_update().filter(
            student_id=student_id, course=course, status=Enrollment.Status.ACTIVE,
        ).first()
        if current and current.course_version_id != course_version.id:
            raise ValidationError(f"A targeted student already has an active enrollment in another version of {course.name}.")
        if current is None:
            Enrollment.objects.create(
                student_id=student_id, course=course, course_version=course_version,
                status=Enrollment.Status.ACTIVE,
            )
            created_count += 1
        else:
            existing_count += 1
    assignment.enrollment_outcome = {"created": created_count, "existing": existing_count, "targeted": len(student_ids)}
    return assignment


def upsert_external_mapping(*, actor, user, provider, external_user_id, metadata=None):
    if actor != user and not actor.has_perm("students.manage_students"):
        raise PermissionDenied("You cannot manage this external mapping.")
    mapping, _ = ExternalUserMapping.objects.update_or_create(
        provider=provider, external_user_id=external_user_id,
        defaults={"user": user, "metadata": metadata or {}},
    )
    return mapping
