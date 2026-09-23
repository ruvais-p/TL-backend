from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.constants import GroupName
from accounts.models import User
from curriculum.models import Chapter, Course, CourseVersion, LearningActivity, Program, Subtopic
from students.models import Enrollment

from .models import (
    ActivityProgress, CareerOpportunity, ChapterProgress, CourseProgress,
    SubtopicProgress,
)
from .services import ProgressService

# Create your tests here.


class ProgressServiceTests(TestCase):
    def setUp(self):
        call_command("setup_groups", verbosity=0)
        self.student = User.objects.create_user(email="progress-student@example.com", password="pass12345")
        self.student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        program = Program.objects.create(name="Progress", code="progress-program", status="PUBLISHED")
        course = Course.objects.create(program=program, name="Progress course", code="progress-course", status="PUBLISHED")
        version = CourseVersion.objects.create(course=course, version_number=1, name="v1", status="PUBLISHED")
        chapter = Chapter.objects.create(course_version=version, title="Chapter", slug="chapter", chapter_number=1, display_order=1, status="PUBLISHED")
        subtopic = Subtopic.objects.create(chapter=chapter, title="Subtopic", slug="subtopic", display_order=1, status="PUBLISHED")
        self.activity = LearningActivity.objects.create(subtopic=subtopic, title="Activity", activity_type="READING", display_order=1, status="PUBLISHED")
        self.enrollment = Enrollment.objects.create(student=self.student, course=course, course_version=version)

    def test_completion_propagates_to_all_levels(self):
        ProgressService.complete_activity(student=self.student, activity=self.activity, enrollment=self.enrollment)
        activity = ActivityProgress.objects.get(enrollment=self.enrollment, activity=self.activity)
        self.assertEqual(activity.progress_percentage, 100)
        self.assertEqual(SubtopicProgress.objects.get(enrollment=self.enrollment).status, "COMPLETED")
        self.assertEqual(ChapterProgress.objects.get(enrollment=self.enrollment).progress_percentage, 100)
        self.assertEqual(CourseProgress.objects.get(enrollment=self.enrollment).progress_percentage, 100)

    def test_progress_api_requires_enrollment_and_returns_snapshot(self):
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.post(f"/api/v1/activities/{self.activity.id}/progress/", {"progress_percentage": 50, "time_spent_seconds": 30}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["progress_percentage"], "50.00")
        self.assertEqual(client.get("/api/v1/me/progress/").status_code, 200)

    def test_student_can_list_own_activity_progress_for_a_course(self):
        ProgressService.record_activity_progress(
            student=self.student,
            activity=self.activity,
            enrollment=self.enrollment,
            progress_percentage=50,
        )
        other_student = User.objects.create_user(email="other-progress@example.com", password="pass12345")
        other_student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        other_enrollment = Enrollment.objects.create(
            student=other_student,
            course=self.enrollment.course,
            course_version=self.enrollment.course_version,
        )
        ProgressService.record_activity_progress(
            student=other_student,
            activity=self.activity,
            enrollment=other_enrollment,
            progress_percentage=100,
        )

        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get(
            "/api/v1/me/activity-progress/",
            {"course": str(self.enrollment.course_id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["activity"], self.activity.id)
        self.assertEqual(response.data[0]["progress_percentage"], "50.00")

    def test_admin_can_review_activity_progress(self):
        ProgressService.record_activity_progress(
            student=self.student,
            activity=self.activity,
            enrollment=self.enrollment,
            progress_percentage=50,
        )
        admin = User.objects.create_user(
            email="progress-admin@example.com", password="StrongPass123!"
        )
        admin.groups.add(Group.objects.get(name=GroupName.ADMIN))
        client = APIClient()
        client.force_authenticate(admin)

        response = client.get("/api/v1/activity-progress-records/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["student_email"], self.student.email)
        self.assertEqual(response.data[0]["activity_title"], self.activity.title)

    def test_super_admin_can_manage_career_opportunities(self):
        super_admin = User.objects.create_user(
            email="career-admin@example.com", password="StrongPass123!"
        )
        super_admin.groups.add(Group.objects.get(name=GroupName.SUPER_ADMIN))
        client = APIClient()
        client.force_authenticate(super_admin)

        response = client.post(
            "/api/v1/career-opportunities/",
            {
                "title": "Analyst internship",
                "kind": "internship",
                "summary": "Apply optimization skills.",
                "url": "https://example.com/careers/analyst",
                "is_published": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(
            CareerOpportunity.objects.filter(title="Analyst internship").exists()
        )
