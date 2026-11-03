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
    def _enrollment(student, learning_check, lock=False):
        version = learning_check.chapter.course_version
        queryset = Enrollment.objects.select_for_update() if lock else Enrollment.objects.all()
        enrollment = queryset.filter(student=student, course=version.course, course_version=version, status=Enrollment.Status.ACTIVE, expires_at__isnull=True).first()
        if enrollment is None:
            enrollment = queryset.filter(student=student, course=version.course, course_version=version, status=Enrollment.Status.ACTIVE, expires_at__gt=timezone.now()).first()
        if enrollment is None:
            raise PermissionDenied("An active enrollment for this course version is required.")
        return enrollment

    @classmethod
    @transaction.atomic
    def start_attempt(cls, *, student, learning_check):
        # Locking the enrollment row serializes concurrent starts; locking the
        # attempts themselves locks nothing before the first attempt exists.
        cls._enrollment(student, learning_check, lock=True)
        if learning_check.status != "PUBLISHED":
            raise PermissionDenied("This learning check is not published.")
        count = AssessmentAttempt.objects.filter(student=student, learning_check=learning_check).count()
        if count >= learning_check.max_attempts:
            raise ValidationError("Maximum attempts exceeded.")
        links = learning_check.questions.select_related("question").all()
        max_score = sum((link.marks for link in links), Decimal("0"))
        return AssessmentAttempt.objects.create(student=student, learning_check=learning_check, attempt_number=count + 1, max_score=max_score)

    @staticmethod
    def _is_correct(question, answer):
        expected = [option.id for option in question.options.all() if option.is_correct]
        selected = answer if isinstance(answer, list) else [answer]
        if question.question_type == "MULTI_SELECT":
            return set(str(v) for v in selected) == set(str(v) for v in expected)
        if question.question_type in {"MCQ", "TRUE_FALSE"}:
            return len(selected) == 1 and str(selected[0]) in {str(v) for v in expected}
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
        links = {
            str(link.question_id): link
            for link in attempt.learning_check.questions.select_related("question").prefetch_related("question__options")
        }
        # One answer per question: repeated entries must never add marks twice.
        submitted = {}
        for item in answers:
            question_id = str(item.get("question"))
            if question_id not in links:
                raise ValidationError("Answer contains a question outside this learning check.")
            if question_id in submitted:
                raise ValidationError("Each question can only be answered once.")
            submitted[question_id] = item.get("answer")
        score = Decimal("0")
        for question_id, answer in submitted.items():
            link = links[question_id]
            correct = cls._is_correct(link.question, answer)
            marks = link.marks if correct else Decimal("0")
            AssessmentAnswer.objects.update_or_create(attempt=attempt, question=link.question, defaults={"answer": answer, "is_correct": correct, "marks_awarded": marks})
            score += marks
        score, percentage = cls._bounded(score, attempt.max_score)
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
    def _bounded(score, max_score):
        if not max_score:
            return score, Decimal("0")
        score = min(score, max_score)
        return score, min(Decimal("100"), (score * 100 / max_score).quantize(Decimal("0.01")))

    @classmethod
    def calculate_score(cls, attempt):
        score = sum((answer.marks_awarded for answer in attempt.answers.all()), Decimal("0"))
        return cls._bounded(score, attempt.max_score)

    @classmethod
    def complete_learning_check(cls, attempt):
        enrollment = cls._enrollment(attempt.student, attempt.learning_check)
        progress, _ = ChapterProgress.objects.get_or_create(enrollment=enrollment, chapter=attempt.learning_check.chapter)
        progress = ChapterProgress.objects.select_for_update().get(pk=progress.pk)
        # Keep the best result: a failed retry must not undo an earlier pass.
        already_passed = progress.learning_check_status == "COMPLETED"
        progress.learning_check_status = "COMPLETED" if attempt.passed or already_passed else "FAILED"
        previous = progress.learning_check_score
        progress.learning_check_score = attempt.percentage if previous is None else max(previous, attempt.percentage)
        progress.save(update_fields=["learning_check_status", "learning_check_score", "updated_at"])
        ProgressService.recalculate_chapter(enrollment=enrollment, chapter=attempt.learning_check.chapter)
