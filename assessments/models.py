import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from curriculum.models import Chapter, Subtopic


class TimestampedUUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Question(TimestampedUUIDModel):
    class QuestionType(models.TextChoices):
        MCQ = "MCQ", "Multiple choice"
        MULTI_SELECT = "MULTI_SELECT", "Multiple select"
        TRUE_FALSE = "TRUE_FALSE", "True/false"
        NUMERIC = "NUMERIC", "Numeric"
        SHORT_TEXT = "SHORT_TEXT", "Short text"
        LONG_TEXT = "LONG_TEXT", "Long text"
        MATH_EXPRESSION = "MATH_EXPRESSION", "Math expression"

    question_type = models.CharField(max_length=30, choices=QuestionType.choices)
    question_text = models.TextField()
    explanation = models.TextField(blank=True)
    difficulty = models.CharField(max_length=30, default="MEDIUM")
    marks = models.DecimalField(max_digits=6, decimal_places=2, default=1, validators=[MinValueValidator(0)])
    subject = models.CharField(max_length=100, blank=True)
    grade = models.CharField(max_length=40, blank=True)
    chapter = models.ForeignKey(Chapter, null=True, blank=True, on_delete=models.PROTECT, related_name="questions")
    subtopic = models.ForeignKey(Subtopic, null=True, blank=True, on_delete=models.PROTECT, related_name="questions")
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default="DRAFT", db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions_created")

    class Meta:
        permissions = [("grade_assessment", "Can grade assessments")]
        indexes = [models.Index(fields=["question_type", "status"], name="question_type_status_idx")]


class QuestionOption(TimestampedUUIDModel):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ["display_order", "created_at"]
        constraints = [models.UniqueConstraint(fields=["question", "display_order"], name="unique_question_option_order")]


class CaseStudy(TimestampedUUIDModel):
    chapter = models.OneToOneField(Chapter, on_delete=models.PROTECT, related_name="case_study")
    title = models.CharField(max_length=255)
    introduction = models.TextField(blank=True)
    content = models.JSONField(default=dict, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=0)
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])
    status = models.CharField(max_length=20, default="DRAFT", db_index=True)


class CaseStudyQuestion(TimestampedUUIDModel):
    case_study = models.ForeignKey(CaseStudy, on_delete=models.CASCADE, related_name="questions")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="case_study_links")
    display_order = models.PositiveIntegerField(default=0)
    marks = models.DecimalField(max_digits=6, decimal_places=2, default=1, validators=[MinValueValidator(0)])
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order"]
        constraints = [models.UniqueConstraint(fields=["case_study", "question"], name="unique_case_study_question")]


class LearningCheck(TimestampedUUIDModel):
    chapter = models.OneToOneField(Chapter, on_delete=models.PROTECT, related_name="learning_check")
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=70, validators=[MinValueValidator(0), MaxValueValidator(100)])
    max_attempts = models.PositiveIntegerField(default=3)
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True)
    randomize_questions = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="DRAFT", db_index=True)


class LearningCheckQuestion(TimestampedUUIDModel):
    learning_check = models.ForeignKey(LearningCheck, on_delete=models.CASCADE, related_name="questions")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="learning_check_links")
    display_order = models.PositiveIntegerField(default=0)
    marks = models.DecimalField(max_digits=6, decimal_places=2, default=1, validators=[MinValueValidator(0)])
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order"]
        constraints = [models.UniqueConstraint(fields=["learning_check", "question"], name="unique_learning_check_question")]


class AssessmentAttempt(TimestampedUUIDModel):
    class Status(models.TextChoices):
        STARTED = "STARTED", "Started"
        SUBMITTED = "SUBMITTED", "Submitted"
        GRADED = "GRADED", "Graded"
        ABANDONED = "ABANDONED", "Abandoned"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="learning_check_attempts")
    learning_check = models.ForeignKey(LearningCheck, on_delete=models.PROTECT, related_name="attempts")
    attempt_number = models.PositiveIntegerField()
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED, db_index=True)
    passed = models.BooleanField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "learning_check", "attempt_number"], name="unique_learning_check_attempt")]
        indexes = [models.Index(fields=["student", "learning_check", "status"], name="attempt_stu_check_status_idx")]


class AssessmentAnswer(TimestampedUUIDModel):
    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="assessment_answers")
    answer = models.JSONField(default=dict)
    is_correct = models.BooleanField(null=True, blank=True)
    marks_awarded = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="unique_attempt_question")]
