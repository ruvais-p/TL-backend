from copy import deepcopy

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Chapter, Course, CourseVersion, LearningActivity, Program, PublishStatus, Subtopic


def _require(user, permission: str) -> None:
    if not user.has_perm(permission):
        raise PermissionDenied(f"Missing permission: {permission}")


def create_program(*, actor, **data) -> Program:
    _require(actor, "curriculum.add_program")
    return Program.objects.create(created_by=actor, **data)


def create_course(*, actor, **data) -> Course:
    _require(actor, "curriculum.add_course")
    return Course.objects.create(created_by=actor, updated_by=actor, **data)


def create_course_version(*, actor, **data) -> CourseVersion:
    _require(actor, "curriculum.add_courseversion")
    return CourseVersion.objects.create(created_by=actor, **data)


def create_chapter(*, actor, **data) -> Chapter:
    _require(actor, "curriculum.add_chapter")
    return Chapter.objects.create(**data)


def create_subtopic(*, actor, **data) -> Subtopic:
    _require(actor, "curriculum.add_subtopic")
    return Subtopic.objects.create(**data)


def create_activity(*, actor, **data) -> LearningActivity:
    _require(actor, "curriculum.add_learningactivity")
    return LearningActivity.objects.create(created_by=actor, updated_by=actor, **data)


@transaction.atomic
def publish_course_version(*, actor, version: CourseVersion) -> CourseVersion:
    _require(actor, "curriculum.publish_course")
    locked = CourseVersion.objects.select_for_update().select_related("course", "course__program").get(pk=version.pk)
    if locked.course.program.status != PublishStatus.PUBLISHED:
        raise ValidationError("The parent program must be published first.")
    if not locked.chapters.exists():
        raise ValidationError("A course version must contain at least one chapter before publishing.")
    locked.status = PublishStatus.PUBLISHED
    locked.published_at = timezone.now()
    locked.save(update_fields=["status", "published_at", "updated_at"])
    locked.course.status = PublishStatus.PUBLISHED
    locked.course.updated_by = actor
    locked.course.save(update_fields=["status", "updated_by", "updated_at"])
    return locked


@transaction.atomic
def publish_chapter(*, actor, chapter: Chapter) -> Chapter:
    _require(actor, "curriculum.publish_chapter")
    locked = Chapter.objects.select_for_update().get(pk=chapter.pk)
    locked.status = PublishStatus.PUBLISHED
    locked.save(update_fields=["status", "updated_at"])
    return locked


@transaction.atomic
def duplicate_chapter(*, actor, chapter: Chapter, title: str | None = None) -> Chapter:
    _require(actor, "curriculum.duplicate_chapter")
    source = Chapter.objects.prefetch_related("subtopics__activities").get(pk=chapter.pk)
    next_number = (source.course_version.chapters.order_by("-chapter_number").values_list("chapter_number", flat=True).first() or 0) + 1
    clone = Chapter.objects.create(
        course_version=source.course_version, title=title or f"{source.title} (copy)",
        slug=f"{source.slug}-copy-{next_number}", description=source.description,
        chapter_number=next_number, estimated_minutes=source.estimated_minutes,
        is_required=source.is_required, status=PublishStatus.DRAFT,
        display_order=source.course_version.chapters.count(), completion_rule=deepcopy(source.completion_rule),
    )
    for subtopic in source.subtopics.all():
        subtopic_clone = Subtopic.objects.create(
            chapter=clone, title=subtopic.title, slug=subtopic.slug, description=subtopic.description,
            learning_objectives=deepcopy(subtopic.learning_objectives), estimated_minutes=subtopic.estimated_minutes,
            display_order=subtopic.display_order, is_required=subtopic.is_required, status=PublishStatus.DRAFT,
        )
        for activity in subtopic.activities.all():
            LearningActivity.objects.create(
                subtopic=subtopic_clone, activity_type=activity.activity_type, title=activity.title,
                description=activity.description, display_order=activity.display_order,
                is_required=activity.is_required, estimated_minutes=activity.estimated_minutes,
                completion_rule=deepcopy(activity.completion_rule), status=PublishStatus.DRAFT,
                created_by=actor, updated_by=actor,
            )
    return clone


@transaction.atomic
def duplicate_course(*, actor, course: Course, code: str, name: str | None = None) -> Course:
    _require(actor, "curriculum.duplicate_course")
    source = Course.objects.prefetch_related("versions__chapters__subtopics__activities").get(pk=course.pk)
    clone = Course.objects.create(
        program=source.program, name=name or f"{source.name} (copy)", code=code,
        description=source.description, thumbnail=source.thumbnail, status=PublishStatus.DRAFT,
        display_order=source.display_order, created_by=actor, updated_by=actor,
    )
    for version in source.versions.all():
        version_clone = CourseVersion.objects.create(
            course=clone, version_number=version.version_number, name=version.name,
            status=PublishStatus.DRAFT, created_by=actor,
        )
        for chapter in version.chapters.all():
            chapter_clone = Chapter.objects.create(
                course_version=version_clone, title=chapter.title, slug=chapter.slug,
                description=chapter.description, chapter_number=chapter.chapter_number,
                estimated_minutes=chapter.estimated_minutes, is_required=chapter.is_required,
                status=PublishStatus.DRAFT, display_order=chapter.display_order,
                completion_rule=deepcopy(chapter.completion_rule),
            )
            for subtopic in chapter.subtopics.all():
                subtopic_clone = Subtopic.objects.create(
                    chapter=chapter_clone, title=subtopic.title, slug=subtopic.slug,
                    description=subtopic.description, learning_objectives=deepcopy(subtopic.learning_objectives),
                    estimated_minutes=subtopic.estimated_minutes, display_order=subtopic.display_order,
                    is_required=subtopic.is_required, status=PublishStatus.DRAFT,
                )
                for activity in subtopic.activities.all():
                    LearningActivity.objects.create(
                        subtopic=subtopic_clone, activity_type=activity.activity_type, title=activity.title,
                        description=activity.description, display_order=activity.display_order,
                        is_required=activity.is_required, estimated_minutes=activity.estimated_minutes,
                        completion_rule=deepcopy(activity.completion_rule), status=PublishStatus.DRAFT,
                        created_by=actor, updated_by=actor,
                    )
    return clone


def _reorder(*, actor, model, parent_field: str, parent, ordered_ids: list) -> None:
    _require(actor, f"curriculum.change_{model._meta.model_name}")
    with transaction.atomic():
        rows = list(model.objects.select_for_update().filter(**{parent_field: parent}))
        if set(ordered_ids) != {row.id for row in rows} or len(ordered_ids) != len(rows):
            raise ValidationError("The order must contain every child exactly once.")
        temporary_base = max((row.display_order for row in rows), default=0) + len(rows) + 1
        for offset, row in enumerate(rows):
            row.display_order = temporary_base + offset
        model.objects.bulk_update(rows, ["display_order"])
        for row in rows:
            row.display_order = ordered_ids.index(row.id)
        model.objects.bulk_update(rows, ["display_order"])


def reorder_chapters(*, actor, course_version, ordered_ids):
    _reorder(actor=actor, model=Chapter, parent_field="course_version", parent=course_version, ordered_ids=ordered_ids)


def reorder_subtopics(*, actor, chapter, ordered_ids):
    _reorder(actor=actor, model=Subtopic, parent_field="chapter", parent=chapter, ordered_ids=ordered_ids)


def reorder_activities(*, actor, subtopic, ordered_ids):
    _reorder(actor=actor, model=LearningActivity, parent_field="subtopic", parent=subtopic, ordered_ids=ordered_ids)
