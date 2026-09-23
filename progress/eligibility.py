from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from assessments.models import AssessmentAttempt as LearningCheckAttempt, LearningCheck
from curriculum.models import Course
from django.core.exceptions import ObjectDoesNotExist
from students.models import Enrollment, StudentGroup


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: tuple[str, ...]


@dataclass
class LearnerFactSnapshot:
    group_ids: set[str]
    grades: set[str]
    enrollment_statuses: dict[str, set[str]]
    course_progress: dict[str, Decimal]
    course_names: dict[str, str]
    learning_check_scores: dict[str, Decimal]
    learning_check_names: dict[str, str]

    @classmethod
    def for_user(cls, user):
        memberships = list(
            StudentGroup.objects.filter(memberships__student=user).only("id", "grade")
        )
        enrollments = list(
            Enrollment.objects.filter(student=user)
            .select_related("course", "course_progress")
            .order_by("created_at")
        )
        attempts = list(
            LearningCheckAttempt.objects.filter(
                student=user,
                status__in=[
                    LearningCheckAttempt.Status.SUBMITTED,
                    LearningCheckAttempt.Status.GRADED,
                ],
                percentage__isnull=False,
            ).select_related("learning_check")
        )

        statuses = {}
        progress = {}
        course_names = {}
        for enrollment in enrollments:
            course_id = str(enrollment.course_id)
            statuses.setdefault(course_id, set()).add(enrollment.status)
            course_names[course_id] = enrollment.course.name
            try:
                value = enrollment.course_progress.progress_percentage
            except (AttributeError, ObjectDoesNotExist):
                value = None
            if value is not None:
                progress[course_id] = max(progress.get(course_id, Decimal("0")), value)
            if enrollment.status == Enrollment.Status.COMPLETED:
                progress[course_id] = Decimal("100")

        scores = {}
        check_names = {}
        for attempt in attempts:
            check_id = str(attempt.learning_check_id)
            scores[check_id] = max(
                scores.get(check_id, Decimal("0")), attempt.percentage
            )
            check_names[check_id] = attempt.learning_check.title

        return cls(
            group_ids={str(group.id) for group in memberships},
            grades={group.grade for group in memberships if group.grade},
            enrollment_statuses=statuses,
            course_progress=progress,
            course_names=course_names,
            learning_check_scores=scores,
            learning_check_names=check_names,
        )


def _condition_result(condition, snapshot):
    fact = condition["fact"]
    if fact == "STUDENT_GROUP":
        matched = bool(snapshot.group_ids.intersection(map(str, condition["values"])))
        return matched, "Join one of the required student groups."
    if fact == "GROUP_GRADE":
        required = {str(value) for value in condition["values"]}
        matched = bool(snapshot.grades.intersection(required))
        return matched, f"This opportunity is for grade(s): {', '.join(sorted(required))}."

    if fact.startswith("COURSE_"):
        course_id = str(condition["course_id"])
        course_name = snapshot.course_names.get(course_id, "the required course")
        if fact == "COURSE_ENROLLMENT":
            statuses = snapshot.enrollment_statuses.get(course_id, set())
            required = set(condition["values"])
            return bool(statuses.intersection(required)), f"Enroll in {course_name}."
        if fact == "COURSE_COMPLETION":
            completed = (
                Enrollment.Status.COMPLETED
                in snapshot.enrollment_statuses.get(course_id, set())
                or snapshot.course_progress.get(course_id, Decimal("0")) >= 100
            )
            expected = condition["value"]
            return completed == expected, (
                f"Complete {course_name}." if expected else f"Do not complete {course_name}."
            )
        threshold = Decimal(str(condition["value"]))
        actual = snapshot.course_progress.get(course_id)
        return actual is not None and actual >= threshold, (
            f"Reach {threshold:g}% progress in {course_name}."
        )

    check_id = str(condition["learning_check_id"])
    threshold = Decimal(str(condition["value"]))
    actual = snapshot.learning_check_scores.get(check_id)
    check_name = snapshot.learning_check_names.get(check_id, "the required learning check")
    return actual is not None and actual >= threshold, (
        f"Score at least {threshold:g}% on {check_name}."
    )


def evaluate_eligibility(rules, snapshot):
    if (
        not isinstance(rules, dict)
        or rules.get("version") != 1
        or rules.get("match") not in {"ALL", "ANY"}
        or not isinstance(rules.get("conditions"), list)
        or any(
            not isinstance(condition, dict)
            or condition.get("fact") not in FACT_SCHEMAS
            for condition in rules.get("conditions", [])
        )
    ):
        return EligibilityResult(False, ("Eligibility requirements are unavailable.",))
    conditions = rules["conditions"]
    if not conditions:
        return EligibilityResult(True, ())
    results = [_condition_result(condition, snapshot) for condition in conditions]
    eligible = (
        all(matched for matched, _reason in results)
        if rules["match"] == "ALL"
        else any(matched for matched, _reason in results)
    )
    if eligible:
        return EligibilityResult(True, ())
    return EligibilityResult(
        False, tuple(reason for matched, reason in results if not matched)
    )


FACT_SCHEMAS = {
    "STUDENT_GROUP": {"operator": "IN", "reference": "groups"},
    "GROUP_GRADE": {"operator": "IN", "reference": "grades"},
    "COURSE_ENROLLMENT": {"operator": "IN", "reference": "course_statuses"},
    "COURSE_COMPLETION": {"operator": "EQ", "reference": "course_boolean"},
    "COURSE_PROGRESS": {"operator": "GTE", "reference": "course_percentage"},
    "LEARNING_CHECK_SCORE": {
        "operator": "GTE",
        "reference": "learning_check_percentage",
    },
}


def _valid_uuid(value):
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def validate_eligibility_rules(rules):
    if not isinstance(rules, dict):
        return ["Eligibility rules must be an object."]
    errors = []
    if rules.get("version") != 1:
        errors.append("Only eligibility rule version 1 is supported.")
    if rules.get("match") not in {"ALL", "ANY"}:
        errors.append("Match must be ALL or ANY.")
    conditions = rules.get("conditions")
    if not isinstance(conditions, list):
        errors.append("Conditions must be a list.")
        return errors

    for index, condition in enumerate(conditions):
        prefix = f"Condition {index + 1}"
        if not isinstance(condition, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        fact = condition.get("fact")
        schema = FACT_SCHEMAS.get(fact)
        if schema is None:
            errors.append(f"{prefix} uses an unsupported fact.")
            continue
        if condition.get("operator") != schema["operator"]:
            errors.append(f"{prefix} uses an invalid operator for {fact}.")
            continue

        reference = schema["reference"]
        if reference == "groups":
            values = condition.get("values")
            if not isinstance(values, list) or not values:
                errors.append(f"{prefix} must reference at least one student group.")
            elif not all(_valid_uuid(value) for value in values):
                errors.append(f"{prefix} contains an invalid student group id.")
            elif StudentGroup.objects.filter(id__in=values).count() != len(set(values)):
                errors.append(f"{prefix} references a missing student group.")
        elif reference == "grades":
            values = condition.get("values")
            if not isinstance(values, list) or not values or not all(
                isinstance(value, str) and value.strip() for value in values
            ):
                errors.append(f"{prefix} must contain one or more grade values.")
        elif reference.startswith("course_"):
            course_id = condition.get("course_id")
            if not _valid_uuid(course_id) or not Course.objects.filter(id=course_id).exists():
                errors.append(f"{prefix} references a missing course.")
                continue
            if reference == "course_statuses":
                values = condition.get("values")
                valid_statuses = set(Enrollment.Status.values)
                if not isinstance(values, list) or not values or not set(values) <= valid_statuses:
                    errors.append(f"{prefix} contains an invalid enrollment status.")
            elif reference == "course_boolean" and not isinstance(
                condition.get("value"), bool
            ):
                errors.append(f"{prefix} must compare completion with true or false.")
            elif reference == "course_percentage":
                value = condition.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                    errors.append(f"{prefix} percentage must be between 0 and 100.")
        elif reference == "learning_check_percentage":
            check_id = condition.get("learning_check_id")
            if not _valid_uuid(check_id) or not LearningCheck.objects.filter(id=check_id).exists():
                errors.append(f"{prefix} references a missing learning check.")
                continue
            value = condition.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
                errors.append(f"{prefix} percentage must be between 0 and 100.")
    return errors
