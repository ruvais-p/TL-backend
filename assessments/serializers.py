from rest_framework import serializers

from .models import (
    AssessmentAnswer, AssessmentAttempt, CaseStudy, CaseStudyQuestion,
    LearningCheck, LearningCheckQuestion, Question, QuestionOption,
)


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = "__all__"


class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = "__all__"


class LearningCheckQuestionSerializer(serializers.ModelSerializer):
    question_detail = QuestionSerializer(source="question", read_only=True)

    class Meta:
        model = LearningCheckQuestion
        fields = "__all__"


class LearningCheckSerializer(serializers.ModelSerializer):
    questions = LearningCheckQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = LearningCheck
        fields = "__all__"


class StudentQuestionOptionSerializer(serializers.ModelSerializer):
    """Assessment options safe to send before a student submits an attempt."""

    class Meta:
        model = QuestionOption
        fields = ("id", "option_text", "display_order")


class StudentQuestionSerializer(serializers.ModelSerializer):
    options = StudentQuestionOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = (
            "id", "question_type", "question_text", "difficulty", "marks",
            "subject", "grade", "chapter", "subtopic", "status", "options",
        )


class StudentLearningCheckQuestionSerializer(serializers.ModelSerializer):
    question_detail = StudentQuestionSerializer(source="question", read_only=True)

    class Meta:
        model = LearningCheckQuestion
        fields = ("id", "question", "question_detail", "display_order", "marks", "is_required")


class StudentLearningCheckSerializer(serializers.ModelSerializer):
    questions = StudentLearningCheckQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = LearningCheck
        fields = (
            "id", "chapter", "title", "instructions", "passing_score",
            "max_attempts", "time_limit_minutes", "randomize_questions",
            "status", "questions",
        )


class CaseStudySerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseStudy
        fields = "__all__"


class CaseStudyQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseStudyQuestion
        fields = "__all__"


class AssessmentAttemptSerializer(serializers.ModelSerializer):
    review = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentAttempt
        fields = "__all__"
        read_only_fields = ("student", "attempt_number", "score", "max_score", "percentage", "status", "passed", "submitted_at")

    def get_review(self, obj):
        """Per-question feedback for a graded attempt.

        Learners always see which answers were right. Explanations (which often
        reveal the answer) appear once they have passed or used every attempt.
        """
        if obj.status != AssessmentAttempt.Status.GRADED:
            return None
        used = AssessmentAttempt.objects.filter(student_id=obj.student_id, learning_check_id=obj.learning_check_id).count()
        reveal = bool(obj.passed) or used >= obj.learning_check.max_attempts
        return [
            {
                "question": str(answer.question_id),
                "is_correct": answer.is_correct,
                "marks_awarded": answer.marks_awarded,
                "explanation": answer.question.explanation if reveal else "",
            }
            for answer in obj.answers.select_related("question").all()
        ]


class SubmitAttemptSerializer(serializers.Serializer):
    attempt_id = serializers.UUIDField(required=False)
    answers = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    time_spent_seconds = serializers.IntegerField(min_value=0, required=False, default=0)


class AssessmentAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentAnswer
        fields = "__all__"


class StaffAssessmentAttemptSerializer(serializers.ModelSerializer):
    student_email = serializers.EmailField(source="student.email", read_only=True)
    learning_check_title = serializers.CharField(
        source="learning_check.title", read_only=True
    )

    class Meta:
        model = AssessmentAttempt
        fields = tuple(field.name for field in AssessmentAttempt._meta.fields) + (
            "student_email",
            "learning_check_title",
        )
        read_only_fields = fields


class StaffAssessmentAnswerSerializer(serializers.ModelSerializer):
    student_email = serializers.EmailField(
        source="attempt.student.email", read_only=True
    )
    question_text = serializers.CharField(
        source="question.question_text", read_only=True
    )

    class Meta:
        model = AssessmentAnswer
        fields = tuple(field.name for field in AssessmentAnswer._meta.fields) + (
            "student_email",
            "question_text",
        )
        read_only_fields = fields
