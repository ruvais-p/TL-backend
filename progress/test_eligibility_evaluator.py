from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model

from progress.eligibility import EligibilityResult, LearnerFactSnapshot, evaluate_eligibility


class EligibilityEvaluatorTests(TestCase):
    def setUp(self):
        self.snapshot = LearnerFactSnapshot(
            group_ids={"11111111-1111-1111-1111-111111111111"},
            grades={"11"},
            enrollment_statuses={"course-1": {"ACTIVE"}, "course-2": {"COMPLETED"}},
            course_progress={"course-1": Decimal("85"), "course-2": Decimal("100")},
            course_names={"course-1": "Operations", "course-2": "Finance"},
            learning_check_scores={"check-1": Decimal("78")},
            learning_check_names={"check-1": "Optimization check"},
        )

    def evaluate(self, conditions, match="ALL"):
        return evaluate_eligibility(
            {"version": 1, "match": match, "conditions": conditions}, self.snapshot
        )

    def test_every_fact_evaluates_true_from_snapshot(self):
        conditions = [
            {
                "fact": "STUDENT_GROUP",
                "operator": "IN",
                "values": ["11111111-1111-1111-1111-111111111111"],
            },
            {"fact": "GROUP_GRADE", "operator": "IN", "values": ["11"]},
            {
                "fact": "COURSE_ENROLLMENT",
                "operator": "IN",
                "course_id": "course-1",
                "values": ["ACTIVE"],
            },
            {
                "fact": "COURSE_COMPLETION",
                "operator": "EQ",
                "course_id": "course-2",
                "value": True,
            },
            {
                "fact": "COURSE_PROGRESS",
                "operator": "GTE",
                "course_id": "course-1",
                "value": 80,
            },
            {
                "fact": "LEARNING_CHECK_SCORE",
                "operator": "GTE",
                "learning_check_id": "check-1",
                "value": 70,
            },
        ]

        result = self.evaluate(conditions)
        self.assertEqual(result, EligibilityResult(True, ()))

    def test_all_returns_each_unmet_reason(self):
        conditions = [
            {"fact": "GROUP_GRADE", "operator": "IN", "values": ["12"]},
            {
                "fact": "COURSE_PROGRESS",
                "operator": "GTE",
                "course_id": "course-1",
                "value": 90,
            },
        ]
        result = self.evaluate(conditions)
        self.assertFalse(result.eligible)
        self.assertEqual(len(result.reasons), 2)

    def test_any_succeeds_when_one_condition_matches(self):
        conditions = [
            {"fact": "GROUP_GRADE", "operator": "IN", "values": ["12"]},
            {"fact": "GROUP_GRADE", "operator": "IN", "values": ["11"]},
        ]
        result = self.evaluate(conditions, match="ANY")
        self.assertTrue(result.eligible)

    def test_empty_rules_are_eligible(self):
        self.assertEqual(self.evaluate([]), EligibilityResult(True, ()))

    def test_missing_fact_is_false_without_error(self):
        condition = {
            "fact": "LEARNING_CHECK_SCORE",
            "operator": "GTE",
            "learning_check_id": "missing",
            "value": 50,
        }
        result = self.evaluate([condition])
        self.assertFalse(result.eligible)
        self.assertIn("required learning check", result.reasons[0])


class LearnerFactSnapshotQueryTests(TestCase):
    def test_empty_snapshot_uses_three_bounded_queries(self):
        user = get_user_model().objects.create_user(
            email="snapshot@example.com", password="pass"
        )

        with self.assertNumQueries(3):
            snapshot = LearnerFactSnapshot.for_user(user)

        self.assertEqual(snapshot.group_ids, set())
        self.assertEqual(snapshot.enrollment_statuses, {})
        self.assertEqual(snapshot.learning_check_scores, {})
