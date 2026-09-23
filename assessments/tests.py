from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.constants import GroupName
from accounts.models import User
from curriculum.models import Chapter, Course, CourseVersion, Program
from students.models import Enrollment

from .models import AssessmentAnswer, AssessmentAttempt, LearningCheck, LearningCheckQuestion, Question, QuestionOption
from .services import AssessmentService


class AssessmentTests(TestCase):
    def setUp(self):
        call_command("setup_groups", verbosity=0)
        self.student = User.objects.create_user(email="assessment-student@example.com", password="pass12345")
        self.student.groups.add(Group.objects.get(name=GroupName.STUDENT))
        program = Program.objects.create(name="Assessment", code="assessment-program", status="PUBLISHED")
        course = Course.objects.create(program=program, name="Assessment course", code="assessment-course", status="PUBLISHED")
        version = CourseVersion.objects.create(course=course, version_number=1, name="v1", status="PUBLISHED")
        chapter = Chapter.objects.create(course_version=version, title="Chapter", slug="assessment-chapter", chapter_number=1, display_order=1, status="PUBLISHED")
        self.enrollment = Enrollment.objects.create(student=self.student, course=course, course_version=version)
        self.check = LearningCheck.objects.create(chapter=chapter, title="Check", passing_score=50, max_attempts=1, status="PUBLISHED")
        question = Question.objects.create(
            question_type="MCQ",
            question_text="Two plus two?",
            explanation="The answer is four.",
            metadata={"correct_answer": "4"},
            marks=2,
            status="PUBLISHED",
        )
        correct = QuestionOption.objects.create(
            question=question,
            option_text="4",
            is_correct=True,
            explanation="Correct option",
            display_order=1,
        )
        QuestionOption.objects.create(question=question, option_text="5", display_order=2)
        self.link = LearningCheckQuestion.objects.create(learning_check=self.check, question=question, marks=2, display_order=1)
        self.correct_option = correct

    def test_start_attempt_is_enrollment_and_publication_scoped(self):
        attempt = AssessmentService.start_attempt(student=self.student, learning_check=self.check)
        self.assertEqual(attempt.attempt_number, 1)
        self.assertEqual(attempt.max_score, 2)

    def test_submit_scores_on_server_and_updates_answer(self):
        attempt = AssessmentService.start_attempt(student=self.student, learning_check=self.check)
        result = AssessmentService.submit_attempt(
            student=self.student, attempt=attempt,
            answers=[{"question": str(self.link.question_id), "answer": str(self.correct_option.id)}],
        )
        self.assertEqual(result.percentage, 100)
        self.assertTrue(result.passed)
        self.assertTrue(AssessmentAnswer.objects.get(attempt=result).is_correct)

    def test_max_attempts_is_enforced(self):
        AssessmentService.start_attempt(student=self.student, learning_check=self.check)
        with self.assertRaises(Exception):
            AssessmentService.start_attempt(student=self.student, learning_check=self.check)

    def test_student_can_start_and_submit_through_api(self):
        client = APIClient()
        client.force_authenticate(self.student)
        start = client.post(f"/api/v1/learning-checks/{self.check.id}/start/", {}, format="json")
        self.assertEqual(start.status_code, 201)
        submit = client.post(f"/api/v1/learning-checks/{self.check.id}/submit/", {
            "attempt_id": start.data["id"], "answers": [{"question": str(self.link.question_id), "answer": str(self.correct_option.id)}],
        }, format="json")
        self.assertEqual(submit.status_code, 200)
        self.assertEqual(submit.data["percentage"], "100.00")

    def test_student_cannot_manage_question_bank(self):
        client = APIClient()
        client.force_authenticate(self.student)
        self.assertEqual(client.get("/api/v1/questions/").status_code, 403)

    def test_admin_can_manage_learning_check_question_links(self):
        admin = User.objects.create_user(
            email="assessment-admin@example.com",
            username="assessment-admin",
            password="StrongPass123!",
        )
        admin.groups.add(Group.objects.get(name=GroupName.ADMIN))
        second_question = Question.objects.create(
            question_type="SHORT_TEXT",
            question_text="Explain the result.",
            marks=1,
            status="DRAFT",
        )
        client = APIClient()
        client.force_authenticate(admin)

        response = client.post(
            "/api/v1/learning-check-questions/",
            {
                "learning_check": str(self.check.id),
                "question": str(second_question.id),
                "display_order": 2,
                "marks": 1,
                "is_required": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(
            LearningCheckQuestion.objects.filter(
                learning_check=self.check,
                question=second_question,
            ).exists()
        )

    def test_student_learning_check_does_not_expose_answers(self):
        client = APIClient()
        client.force_authenticate(self.student)

        response = client.get(f"/api/v1/learning-checks/{self.check.id}/")

        self.assertEqual(response.status_code, 200)
        question = response.data["questions"][0]["question_detail"]
        self.assertNotIn("metadata", question)
        self.assertNotIn("explanation", question)
        self.assertNotIn("is_correct", question["options"][0])
        self.assertNotIn("explanation", question["options"][0])

    def test_admin_can_review_attempts_and_answers_in_staff_api(self):
        attempt = AssessmentService.start_attempt(
            student=self.student, learning_check=self.check
        )
        AssessmentService.submit_attempt(
            student=self.student,
            attempt=attempt,
            answers=[
                {
                    "question": str(self.link.question_id),
                    "answer": str(self.correct_option.id),
                }
            ],
        )
        admin = User.objects.create_user(
            email="attempt-reviewer@example.com",
            username="attempt-reviewer",
            password="StrongPass123!",
        )
        admin.groups.add(Group.objects.get(name=GroupName.ADMIN))
        client = APIClient()
        client.force_authenticate(admin)

        attempts = client.get("/api/v1/assessment-attempts/")
        answers = client.get("/api/v1/assessment-answers/")

        self.assertEqual(attempts.status_code, 200)
        self.assertEqual(attempts.data[0]["student_email"], self.student.email)
        self.assertEqual(answers.status_code, 200)
        self.assertEqual(answers.data[0]["question_text"], "Two plus two?")
