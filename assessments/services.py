from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from progress.models import ChapterProgress
from progress.services import ProgressService
from students.models import Enrollment

from .models import AssessmentAnswer, AssessmentAttempt, LearningCheck


class AssessmentService:
    @staticmethod
    def _enrollment(student, learning_check):
        version = learning_check.chapter.course_version
        enrollment = Enrollment.objects.filter(student=student, course=version.course, course_version=version, status=Enrollment.Status.ACTIVE, expires_at__isnull=True).first()
        if enrollment is None:
            enrollment = Enrollment.objects.filter(student=student, course=version.course, course_version=version, status=Enrollment.Status.ACTIVE, expires_at__gt=timezone.now()).first()
        if enrollment is None:
            raise PermissionDenied("An active enrollment for this course version is required.")
        return enrollment

    @classmethod
    @transaction.atomic
    def start_attempt(cls, *, student, learning_check):
        cls._enrollment(student, learning_check)
        if learning_check.status != "PUBLISHED":
            raise PermissionDenied("This learning check is not published.")
        count = AssessmentAttempt.objects.select_for_update().filter(student=student, learning_check=learning_check).count()
        if count >= learning_check.max_attempts:
            raise ValidationError("Maximum attempts exceeded.")
        links = learning_check.questions.select_related("question").all()
        max_score = sum((link.marks for link in links), Decimal("0"))
        return AssessmentAttempt.objects.create(student=student, learning_check=learning_check, attempt_number=count + 1, max_score=max_score)

    @staticmethod
    def _is_correct(question, answer):
        expected = list(question.options.filter(is_correct=True).values_list("id", flat=True))
        selected = answer if isinstance(answer, list) else [answer]
        if question.question_type == "MULTI_SELECT":
            return set(str(v) for v in selected) == set(str(v) for v in expected)
        if question.question_type in {"MCQ", "TRUE_FALSE"}:
            return bool(selected) and str(selected[0]) in {str(v) for v in expected}
        if question.question_type == "NUMERIC":
            try:
                return Decimal(str(answer)) == Decimal(str(question.metadata.get("correct_answer")))
            except (InvalidOperation, TypeError):
                return False
        expected_text = str(question.metadata.get("correct_answer", "")).strip().casefold()
        return bool(expected_text) and str(answer).strip().casefold() == expected_text

    @classmethod
    @transaction.atomic
    def submit_attempt(cls, *, student, attempt, answers, time_spent_seconds=0):
        attempt = AssessmentAttempt.objects.select_for_update().select_related("learning_check__chapter__course_version__course").get(pk=attempt.pk)
        if attempt.student_id != student.id:
            raise PermissionDenied("You can only submit your own attempt.")
        if attempt.status != AssessmentAttempt.Status.STARTED:
            raise ValidationError("This attempt is no longer open.")
        links = {str(link.question_id): link for link in attempt.learning_check.questions.select_related("question")}
        score = Decimal("0")
        for item in answers:
            question_id = str(item.get("question"))
            link = links.get(question_id)
            if link is None:
                raise ValidationError("Answer contains a question outside this learning check.")
            correct = cls._is_correct(link.question, item.get("answer"))
            marks = link.marks if correct else Decimal("0")
            AssessmentAnswer.objects.update_or_create(attempt=attempt, question=link.question, defaults={"answer": item.get("answer"), "is_correct": correct, "marks_awarded": marks})
            score += marks
        percentage = Decimal("0") if not attempt.max_score else (score * 100 / attempt.max_score).quantize(Decimal("0.01"))
        attempt.score = score
        attempt.percentage = percentage
        attempt.passed = percentage >= attempt.learning_check.passing_score
        attempt.status = AssessmentAttempt.Status.GRADED
        attempt.submitted_at = timezone.now()
        attempt.time_spent_seconds = max(0, int(time_spent_seconds or 0))
        attempt.save()
        cls.complete_learning_check(attempt)
        return attempt

    @staticmethod
    def calculate_score(attempt):
        score = sum((answer.marks_awarded for answer in attempt.answers.all()), Decimal("0"))
        return score, (Decimal("0") if not attempt.max_score else (score * 100 / attempt.max_score).quantize(Decimal("0.01")))

    @classmethod
    def complete_learning_check(cls, attempt):
        enrollment = cls._enrollment(attempt.student, attempt.learning_check)
        progress, _ = ChapterProgress.objects.get_or_create(enrollment=enrollment, chapter=attempt.learning_check.chapter)
        progress.learning_check_status = "COMPLETED" if attempt.passed else "FAILED"
        progress.learning_check_score = attempt.percentage
        progress.save(update_fields=["learning_check_status", "learning_check_score", "updated_at"])
        ProgressService.recalculate_chapter(enrollment=enrollment, chapter=attempt.learning_check.chapter)
