from django.test import TestCase

from assessments.models import LearningCheck
from curriculum.models import Chapter, Course, CourseVersion, Program
from progress.eligibility import validate_eligibility_rules
from students.models import Enrollment, StudentGroup


class EligibilityRuleValidationTests(TestCase):
    def setUp(self):
        self.group = StudentGroup.objects.create(
            name="Grade 11", code="grade-11", grade="11", academic_year=2026
        )
        program = Program.objects.create(name="Commerce", code="commerce")
        self.course = Course.objects.create(
            program=program, name="Operations", code="operations"
        )
        version = CourseVersion.objects.create(
            course=self.course, version_number=1, name="Version 1"
        )
        chapter = Chapter.objects.create(
            course_version=version,
            title="Optimization",
            slug="optimization",
            chapter_number=1,
        )
        self.learning_check = LearningCheck.objects.create(
            chapter=chapter, title="Optimization check"
        )

    def rules(self, condition, **overrides):
        rules = {"version": 1, "match": "ALL", "conditions": [condition]}
        rules.update(overrides)
        return rules

    def test_every_supported_fact_accepts_its_documented_shape(self):
        conditions = [
            {"fact": "STUDENT_GROUP", "operator": "IN", "values": [str(self.group.id)]},
            {"fact": "GROUP_GRADE", "operator": "IN", "values": ["11"]},
            {
                "fact": "COURSE_ENROLLMENT",
                "operator": "IN",
                "course_id": str(self.course.id),
                "values": [Enrollment.Status.ACTIVE],
            },
            {
                "fact": "COURSE_COMPLETION",
                "operator": "EQ",
                "course_id": str(self.course.id),
                "value": True,
            },
            {
                "fact": "COURSE_PROGRESS",
                "operator": "GTE",
                "course_id": str(self.course.id),
                "value": 80,
            },
            {
                "fact": "LEARNING_CHECK_SCORE",
                "operator": "GTE",
                "learning_check_id": str(self.learning_check.id),
                "value": 70,
            },
        ]
        self.assertEqual(
            validate_eligibility_rules(
                {"version": 1, "match": "ANY", "conditions": conditions}
            ),
            [],
        )

    def test_unknown_version_fact_and_operator_are_rejected(self):
        self.assertTrue(
            validate_eligibility_rules(
                self.rules(
                    {"fact": "STUDENT_GROUP", "operator": "IN", "values": [str(self.group.id)]},
                    version=2,
                )
            )
        )
        self.assertTrue(
            validate_eligibility_rules(self.rules({"fact": "MAGIC", "operator": "EQ"}))
        )
        self.assertTrue(
            validate_eligibility_rules(
                self.rules({"fact": "GROUP_GRADE", "operator": "GTE", "values": ["11"]})
            )
        )

    def test_missing_incompatible_references_and_ranges_are_rejected(self):
        self.assertTrue(
            validate_eligibility_rules(
                self.rules(
                    {
                        "fact": "COURSE_PROGRESS",
                        "operator": "GTE",
                        "course_id": str(self.group.id),
                        "value": 80,
                    }
                )
            )
        )
        self.assertTrue(
            validate_eligibility_rules(
                self.rules(
                    {
                        "fact": "LEARNING_CHECK_SCORE",
                        "operator": "GTE",
                        "learning_check_id": str(self.learning_check.id),
                        "value": 101,
                    }
                )
            )
        )
