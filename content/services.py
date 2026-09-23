from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from curriculum.models import LearningActivity

from .models import ActivityContent, Experiment, PracticeItem, PracticeSet, Video


def _require(actor, model, action="add"):
    permission = f"content.{action}_{model._meta.model_name}"
    if not actor.has_perm(permission):
        raise PermissionDenied(f"Missing permission: {permission}")


def create_activity_content(*, actor, **data):
    _require(actor, ActivityContent)
    return ActivityContent.objects.create(**data)


def create_video(*, actor, **data):
    _require(actor, Video)
    if data["activity"].activity_type != LearningActivity.ActivityType.CONCEPT_VIDEO:
        raise ValidationError("Video content requires a CONCEPT_VIDEO activity.")
    return Video.objects.create(**data)


def create_experiment(*, actor, **data):
    _require(actor, Experiment)
    allowed = {
        LearningActivity.ActivityType.EXPERIMENT,
        LearningActivity.ActivityType.SIMULATION,
        LearningActivity.ActivityType.INTERACTIVE,
        LearningActivity.ActivityType.INTERACTIVE_WORKSHOP,
    }
    if data["activity"].activity_type not in allowed:
        raise ValidationError("Experiment content requires an experiment, simulation, interactive, or interactive workshop activity.")
    return Experiment.objects.create(**data)


def create_practice_set(*, actor, **data):
    _require(actor, PracticeSet)
    if data["activity"].activity_type != LearningActivity.ActivityType.OBSERVE_LEARN_PRACTICE:
        raise ValidationError("Practice sets require an OBSERVE_LEARN_PRACTICE activity.")
    return PracticeSet.objects.create(**data)


def create_practice_item(*, actor, **data):
    _require(actor, PracticeItem)
    item_type = data.get("item_type")
    video = data.get("video")
    question = data.get("question_reference")
    valid = (
        item_type == PracticeItem.ItemType.VIDEO and video and not question
        or item_type == PracticeItem.ItemType.QUESTION and question and not video
        or item_type == PracticeItem.ItemType.PRACTICE and not video and not question
    )
    if not valid:
        raise ValidationError("Practice item reference does not match its item type.")
    return PracticeItem.objects.create(**data)


@transaction.atomic
def reorder_practice_items(*, actor, practice_set: PracticeSet, ordered_ids: list):
    _require(actor, PracticeItem, "change")
    rows = list(PracticeItem.objects.select_for_update().filter(practice_set=practice_set))
    if len(rows) != len(ordered_ids) or {row.id for row in rows} != set(ordered_ids):
        raise ValidationError("The order must contain every practice item exactly once.")
    temporary = max((row.display_order for row in rows), default=0) + len(rows) + 1
    for offset, row in enumerate(rows):
        row.display_order = temporary + offset
    PracticeItem.objects.bulk_update(rows, ["display_order"])
    for row in rows:
        row.display_order = ordered_ids.index(row.id)
    PracticeItem.objects.bulk_update(rows, ["display_order"])
