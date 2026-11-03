"""Regression tests for the security and data-integrity audit findings."""

import hashlib
import hmac
import time

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.constants import GroupName
from accounts.models import User
from assessments.models import LearningCheck, LearningCheckQuestion, Question, QuestionOption
from assessments.services import AssessmentService
from curriculum.models import Chapter, Course, CourseVersion, LearningActivity, Program, PublishStatus, Subtopic
from curriculum.services import publish_course_version
from progress.models import ActivityProgress, ChapterProgress, SubtopicProgress
from progress.services import ProgressService
from students.models import Enrollment, StudentGroup, StudentGroupMember

STRONG_SSO_SECRET = "regression-sso-secret-0123456789abcdef0123456789"


class AuditRegressionTests(TestCase):
    def setUp(self):
        # Login throttling and single-use SSO markers live in the shared cache.
        cache.clear()
        call_command("setup_groups", verbosity=0)
        self.student = self._user("audit-student@example.com", GroupName.STUDENT)
        self.admin = self._user("audit-admin@example.com", GroupName.ADMIN)
        self.admin.is_superuser = True
        self.admin.save()
        self.program = Program.objects.create(name="Audit", code="audit-program", status=PublishStatus.PUBLISHED)
        self.course = Course.objects.create(program=self.program, name="Audit course", code="audit-course", status=PublishStatus.PUBLISHED)
        self.version = CourseVersion.objects.create(course=self.course, version_number=1, name="v1", status=PublishStatus.PUBLISHED)
        self.chapter = Chapter.objects.create(course_version=self.version, title="Chapter", slug="audit-chapter", chapter_number=1, display_order=1, status=PublishStatus.PUBLISHED)
        self.subtopic = Subtopic.objects.create(chapter=self.chapter, title="Subtopic", slug="audit-subtopic", status=PublishStatus.PUBLISHED)
        self.activities = [
            LearningActivity.objects.create(
                subtopic=self.subtopic, activity_type=LearningActivity.ActivityType.CONCEPT_VIDEO,
                title=f"Activity {index}", display_order=index, status=PublishStatus.PUBLISHED,
            )
            for index in range(2)
        ]
        self.enrollment = Enrollment.objects.create(student=self.student, course=self.course, course_version=self.version)
        self.check = LearningCheck.objects.create(chapter=self.chapter, title="Check", passing_score=70, max_attempts=3, status="PUBLISHED")
        question = Question.objects.create(question_type="MCQ", question_text="2+2?", marks=1, status="PUBLISHED")
        self.correct = QuestionOption.objects.create(question=question, option_text="4", is_correct=True, display_order=1)
        self.wrong = QuestionOption.objects.create(question=question, option_text="5", display_order=2)
        self.link = LearningCheckQuestion.objects.create(learning_check=self.check, question=question, marks=3, display_order=1)

    @staticmethod
    def _user(email, group):
        user = User.objects.create_user(email=email, username=email.split("@")[0], password="pass12345")
        user.groups.add(Group.objects.get(name=group))
        return user

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _answer(self, option):
        return {"question": str(self.link.question_id), "answer": str(option.id)}

    # Assessment scoring
    def test_repeated_answers_cannot_inflate_the_score(self):
        attempt = AssessmentService.start_attempt(student=self.student, learning_check=self.check)
        response = self._client(self.student).post(
            f"/api/v1/learning-checks/{self.check.id}/submit/",
            {"attempt_id": str(attempt.id), "answers": [self._answer(self.correct)] * 5 + [self._answer(self.wrong)]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "STARTED")

    def test_failed_retry_keeps_the_earlier_pass(self):
        first = AssessmentService.start_attempt(student=self.student, learning_check=self.check)
        AssessmentService.submit_attempt(student=self.student, attempt=first, answers=[self._answer(self.correct)])
        second = AssessmentService.start_attempt(student=self.student, learning_check=self.check)
        AssessmentService.submit_attempt(student=self.student, attempt=second, answers=[self._answer(self.wrong)])
        progress = ChapterProgress.objects.get(enrollment=self.enrollment, chapter=self.chapter)
        self.assertEqual(progress.learning_check_status, "COMPLETED")
        self.assertEqual(progress.learning_check_score, 100)

    def test_attempts_beyond_the_limit_return_400(self):
        self.check.max_attempts = 1
        self.check.save()
        client = self._client(self.student)
        self.assertEqual(client.post(f"/api/v1/learning-checks/{self.check.id}/start/", {}, format="json").status_code, 201)
        self.assertEqual(client.post(f"/api/v1/learning-checks/{self.check.id}/start/", {}, format="json").status_code, 400)

    # Progress
    def test_completion_is_monotonic(self):
        activity = self.activities[0]
        ProgressService.complete_activity(student=self.student, activity=activity)
        client = self._client(self.student)
        client.post(f"/api/v1/activities/{activity.id}/start/", {}, format="json")
        client.post(f"/api/v1/activities/{activity.id}/progress/", {"progress_percentage": 10}, format="json")
        row = ActivityProgress.objects.get(enrollment=self.enrollment, activity=activity)
        self.assertEqual(row.status, "COMPLETED")
        self.assertEqual(row.progress_percentage, 100)
        self.assertEqual(SubtopicProgress.objects.get(enrollment=self.enrollment, subtopic=self.subtopic).completed_activities, 1)

    def test_time_spent_accumulates_and_status_is_canonical(self):
        activity = self.activities[1]
        client = self._client(self.student)
        client.post("/api/v1/progress/", {"activity": str(activity.id), "time_spent_seconds": 30, "status": "in_progress"}, format="json")
        client.post("/api/v1/progress/", {"activity": str(activity.id), "time_spent_seconds": 15}, format="json")
        row = ActivityProgress.objects.get(enrollment=self.enrollment, activity=activity)
        self.assertEqual(row.time_spent_seconds, 45)
        self.assertEqual(row.status, "IN_PROGRESS")
        bogus = client.post(f"/api/v1/activities/{activity.id}/bogus/", {}, format="json")
        self.assertEqual(bogus.status_code, 404)
        invalid = client.post("/api/v1/progress/", {"activity": str(activity.id), "status": "WHATEVER"}, format="json")
        self.assertEqual(invalid.status_code, 400)

    # Version pinning
    def test_learners_stay_on_their_enrolled_version(self):
        v2 = CourseVersion.objects.create(course=self.course, version_number=2, name="v2", status=PublishStatus.DRAFT)
        Chapter.objects.create(course_version=v2, title="New", slug="audit-new", chapter_number=1, display_order=1, status=PublishStatus.PUBLISHED)
        publish_course_version(actor=self.admin, version=v2)
        response = self._client(self.student).get(f"/api/v1/courses/{self.course.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["published_version"]["id"], str(self.version.id))
        self.assertEqual([version["id"] for version in response.data["versions"]], [str(self.version.id)])

    # Enrollment data safety and domain errors
    def test_deleting_an_enrollment_cancels_it_and_keeps_progress(self):
        ProgressService.complete_activity(student=self.student, activity=self.activities[0])
        response = self._client(self.admin).delete(f"/api/v1/enrollments/{self.enrollment.id}/")
        self.assertEqual(response.status_code, 204)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.CANCELLED)
        self.assertTrue(ActivityProgress.objects.filter(enrollment=self.enrollment).exists())

    def test_invalid_group_member_returns_400_not_500(self):
        group = StudentGroup.objects.create(name="G", code="g-audit", academic_year=2026)
        client = self._client(self.admin)
        self.assertEqual(client.post(f"/api/v1/student-groups/{group.id}/members/", {"student": "not-a-uuid"}, format="json").status_code, 400)
        self.assertEqual(client.post(f"/api/v1/student-groups/{group.id}/members/", {"student": str(self.admin.id)}, format="json").status_code, 400)

    # Authorization
    def test_students_only_see_their_own_teachers(self):
        mine = self._user("audit-teacher-mine@example.com", GroupName.TEACHER)
        self._user("audit-teacher-other@example.com", GroupName.TEACHER)
        group = StudentGroup.objects.create(name="Mine", code="mine-audit", academic_year=2026, teacher=mine)
        StudentGroupMember.objects.create(student_group=group, student=self.student)
        response = self._client(self.student).get("/api/v1/teachers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["email"] for row in response.data], [mine.email])

    def test_staff_summary_is_staff_only(self):
        self.assertEqual(self._client(self.student).get("/api/v1/auth/staff-summary/").status_code, 403)

    # Moodle SSO
    def _moodle(self, email, external_id="moodle-1", secret=STRONG_SSO_SECRET):
        timestamp = int(time.time())
        signature = hmac.new(secret.encode(), f"{external_id}|{email}|{timestamp}".encode(), hashlib.sha256).hexdigest()
        return APIClient().post(
            "/api/v1/auth/moodle/exchange/",
            {"moodle_user_id": external_id, "email": email, "timestamp": timestamp, "signature": signature},
            format="json",
        )

    @override_settings(MOODLE_SSO_SECRET=STRONG_SSO_SECRET)
    def test_moodle_cannot_take_over_a_staff_account_by_email(self):
        self.assertEqual(self._moodle(self.admin.email).status_code, 403)

    @override_settings(MOODLE_SSO_SECRET=STRONG_SSO_SECRET)
    def test_moodle_signatures_are_single_use(self):
        timestamp = int(time.time())
        payload = {"moodle_user_id": "moodle-9", "email": "new-learner@example.com", "timestamp": timestamp}
        payload["signature"] = hmac.new(
            STRONG_SSO_SECRET.encode(), f"moodle-9|new-learner@example.com|{timestamp}".encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(APIClient().post("/api/v1/auth/moodle/exchange/", payload, format="json").status_code, 200)
        self.assertEqual(APIClient().post("/api/v1/auth/moodle/exchange/", payload, format="json").status_code, 401)

    @override_settings(MOODLE_SSO_SECRET="tella-dev-sso-secret-change-me")
    def test_placeholder_moodle_secret_disables_sso(self):
        self.assertEqual(self._moodle("someone@example.com", secret="tella-dev-sso-secret-change-me").status_code, 401)
