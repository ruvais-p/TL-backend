from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from accounts.constants import GroupName
from students.models import Enrollment

from .models import Chapter, Course, CourseVersion, LearningActivity, PublishStatus, Subtopic


def is_student(user) -> bool:
    return user.groups.filter(name=GroupName.STUDENT).exists() and not user.is_superuser


def accessible_courses(user) -> QuerySet[Course]:
    queryset = Course.objects.select_related("program", "thumbnail", "created_by", "updated_by")
    if is_student(user):
        enrolled = Enrollment.objects.filter(
            student=user, status=Enrollment.Status.ACTIVE,
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).values("course_id")
        queryset = queryset.filter(
            id__in=enrolled, status=PublishStatus.PUBLISHED, program__status=PublishStatus.PUBLISHED,
            versions__status=PublishStatus.PUBLISHED,
        ).distinct()
    return queryset


def course_structure_queryset(user) -> QuerySet[Course]:
    published_only = is_student(user)
    user._curriculum_is_student = published_only
    activities = LearningActivity.objects.select_related("content", "experiment").order_by("display_order")
    subtopics = Subtopic.objects.order_by("display_order")
    chapters = Chapter.objects.order_by("display_order")
    versions = CourseVersion.objects.order_by("-version_number")
    if published_only:
        activities = activities.filter(status=PublishStatus.PUBLISHED)
        subtopics = subtopics.filter(status=PublishStatus.PUBLISHED)
        chapters = chapters.filter(status=PublishStatus.PUBLISHED)
        versions = versions.filter(status=PublishStatus.PUBLISHED)
    subtopics = subtopics.prefetch_related(Prefetch("activities", queryset=activities))
    chapters = chapters.prefetch_related(Prefetch("subtopics", queryset=subtopics))
    versions = versions.prefetch_related(Prefetch("chapters", queryset=chapters))
    return accessible_courses(user).prefetch_related(Prefetch("versions", queryset=versions))


def accessible_chapters(user) -> QuerySet[Chapter]:
    queryset = Chapter.objects.select_related("course_version__course__program")
    if is_student(user):
        course_ids = accessible_courses(user).values("id")
        queryset = queryset.filter(
            course_version__course_id__in=course_ids,
            course_version__status=PublishStatus.PUBLISHED,
            status=PublishStatus.PUBLISHED,
        )
    return queryset


def accessible_subtopics(user) -> QuerySet[Subtopic]:
    queryset = Subtopic.objects.select_related("chapter__course_version__course")
    if is_student(user):
        queryset = queryset.filter(chapter_id__in=accessible_chapters(user).values("id"), status=PublishStatus.PUBLISHED)
    return queryset


def accessible_activities(user) -> QuerySet[LearningActivity]:
    queryset = LearningActivity.objects.select_related(
        "subtopic__chapter__course_version__course", "content", "experiment"
    )
    if is_student(user):
        queryset = queryset.filter(subtopic_id__in=accessible_subtopics(user).values("id"), status=PublishStatus.PUBLISHED)
    return queryset
