from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.constants import GroupName
from accounts.models import User
from curriculum.models import Course, CourseVersion, Program, PublishStatus

from .models import CourseAssignment, Enrollment, ExternalUserMapping, StudentGroup, StudentGroupMember
from .services import add_student_to_group, create_course_assignment, create_enrollment


class StudentDomainFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_groups", verbosity=0)
        cls.admin = User.objects.create_user(email="admin4@example.com", password="pass12345")
        cls.teacher = User.objects.create_user(email="teacher4@example.com", password="pass12345")
        cls.other_teacher = User.objects.create_user(email="teacher-other@example.com", password="pass12345")
        cls.student = User.objects.create_user(email="student4@example.com", password="pass12345")
        cls.other_student = User.objects.create_user(email="student-other@example.com", password="pass12345")
        cls.admin.groups.add(Group.objects.get(name=GroupName.ADMIN))
        cls.teacher.groups.add(Group.objects.get(name=GroupName.TEACHER))
        cls.other_teacher.groups.add(Group.objects.get(name=GroupName.TEACHER))
        cls.student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        cls.other_student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        cls.program = Program.objects.create(name="Grade 9", code="grade-9", status=PublishStatus.PUBLISHED)
        cls.course = Course.objects.create(program=cls.program, name="Math", code="math-4", status=PublishStatus.PUBLISHED)
        cls.version = CourseVersion.objects.create(course=cls.course, version_number=2026, name="2026", status=PublishStatus.PUBLISHED)
        cls.other_version = CourseVersion.objects.create(course=cls.course, version_number=2027, name="2027")
        cls.group = StudentGroup.objects.create(name="Grade 9A", code="G9A", grade="9", academic_year=2026, teacher=cls.teacher)
        cls.other_group = StudentGroup.objects.create(name="Grade 9B", code="G9B", grade="9", academic_year=2026, teacher=cls.other_teacher)
        StudentGroupMember.objects.create(student_group=cls.group, student=cls.student)
        StudentGroupMember.objects.create(student_group=cls.other_group, student=cls.other_student)


class StudentDomainServiceTests(StudentDomainFixture):
    def test_group_membership_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentGroupMember.objects.create(student_group=self.group, student=self.student)

    def test_assignment_requires_exactly_one_target(self):
        with self.assertRaises(ValidationError):
            create_course_assignment(actor=self.admin, course=self.course, course_version=self.version)

    def test_group_assignment_creates_versioned_enrollment(self):
        assignment = create_course_assignment(
            actor=self.admin, course=self.course, course_version=self.version, student_group=self.group,
        )
        self.assertEqual(assignment.assigned_by, self.admin)
        self.assertTrue(Enrollment.objects.filter(student=self.student, course_version=self.version).exists())
        self.assertEqual(assignment.enrollment_outcome, {"created": 1, "existing": 0, "targeted": 1})

    def test_empty_group_assignment_reports_zero_enrollments(self):
        empty = StudentGroup.objects.create(name="Empty", code="EMPTY", academic_year=2026)
        assignment = create_course_assignment(actor=self.admin, course=self.course, course_version=self.version, student_group=empty)
        self.assertEqual(assignment.enrollment_outcome, {"created": 0, "existing": 0, "targeted": 0})

    def test_group_assignment_preserves_matching_enrollment(self):
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        assignment = create_course_assignment(actor=self.admin, course=self.course, course_version=self.version, student_group=self.group)
        self.assertEqual(assignment.enrollment_outcome["existing"], 1)
        self.assertEqual(Enrollment.objects.filter(student=self.student, course=self.course).count(), 1)

    def test_group_assignment_rolls_back_on_conflicting_version(self):
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.other_version)
        with self.assertRaises(ValidationError):
            create_course_assignment(actor=self.admin, course=self.course, course_version=self.version, student_group=self.group)
        self.assertFalse(CourseAssignment.objects.filter(student_group=self.group).exists())

    def test_new_member_inherits_active_group_assignment(self):
        create_course_assignment(actor=self.admin, course=self.course, course_version=self.version, student_group=self.group)
        add_student_to_group(actor=self.admin, student_group=self.group, student=self.other_student)
        self.assertTrue(Enrollment.objects.filter(student=self.other_student, course_version=self.version).exists())

    def test_new_member_conflict_rolls_back_membership(self):
        create_course_assignment(actor=self.admin, course=self.course, course_version=self.version, student_group=self.group)
        Enrollment.objects.create(student=self.other_student, course=self.course, course_version=self.other_version)
        with self.assertRaises(ValidationError):
            add_student_to_group(actor=self.admin, student_group=self.group, student=self.other_student)
        self.assertFalse(StudentGroupMember.objects.filter(student_group=self.group, student=self.other_student).exists())

    def test_enrollment_rejects_course_version_mismatch(self):
        other_course = Course.objects.create(program=self.program, name="Science", code="science-4")
        with self.assertRaises(ValidationError):
            create_enrollment(
                actor=self.admin, student=self.student, course=other_course, course_version=self.version,
            )

    def test_only_one_active_course_enrollment(self):
        Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrollment.objects.create(student=self.student, course=self.course, course_version=self.other_version)


class StudentDomainApiTests(StudentDomainFixture):
    def setUp(self):
        self.client = APIClient()

    def test_teacher_only_sees_students_in_assigned_group(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.get(reverse("student-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [str(self.student.id)])
        self.assertEqual(self.client.get(reverse("student-detail", args=[self.other_student.id])).status_code, 404)

    def test_student_only_sees_own_enrollment(self):
        own = Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        Enrollment.objects.create(student=self.other_student, course=self.course, course_version=self.version)
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("enrollment-list"))
        self.assertEqual([row["id"] for row in response.data], [str(own.id)])

    def test_expired_enrollment_does_not_grant_course_access(self):
        Enrollment.objects.create(
            student=self.student, course=self.course, course_version=self.version,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get(reverse("course-detail", args=[self.course.id])).status_code, 404)

    def test_admin_assigns_course_to_group_api(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(reverse("course-assignment-list"), {
            "course": str(self.course.id), "course_version": str(self.version.id),
            "student_group": str(self.group.id), "status": CourseAssignment.Status.ACTIVE,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Enrollment.objects.filter(student=self.student, course_version=self.version).exists())
        self.assertEqual(response.data["enrollment_outcome"]["created"], 1)

    def test_assignment_filter_is_scoped_to_group(self):
        own = CourseAssignment.objects.create(course=self.course, course_version=self.version, student_group=self.group, assigned_by=self.admin)
        CourseAssignment.objects.create(course=self.course, course_version=self.version, student_group=self.other_group, assigned_by=self.admin)
        self.client.force_authenticate(self.teacher)
        response = self.client.get(reverse("course-assignment-list"), {"student_group": self.group.id})
        self.assertEqual([row["id"] for row in response.data], [str(own.id)])

    def test_removing_membership_preserves_enrollment(self):
        enrollment = Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        membership = StudentGroupMember.objects.get(student_group=self.group, student=self.student)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.delete(reverse("student-group-member-detail", args=[membership.id])).status_code, 204)
        self.assertTrue(Enrollment.objects.filter(pk=enrollment.pk).exists())

    def test_student_cannot_create_assignment(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(reverse("course-assignment-list"), {
            "course": str(self.course.id), "course_version": str(self.version.id),
            "student": str(self.student.id),
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_external_mapping_is_provider_scoped_and_unique(self):
        mapping = ExternalUserMapping.objects.create(
            user=self.student, provider=ExternalUserMapping.Provider.MOODLE, external_user_id="42",
        )
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("external-user-mapping-list"))
        self.assertEqual([row["id"] for row in response.data], [str(mapping.id)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExternalUserMapping.objects.create(
                user=self.other_student, provider=ExternalUserMapping.Provider.MOODLE, external_user_id="42",
            )
