from curriculum.selectors import accessible_activities, is_student

from .models import ActivityContent, Experiment, PracticeItem, PracticeSet, Video


def accessible_content(user):
    queryset = ActivityContent.objects.select_related("activity")
    return queryset.filter(activity__in=accessible_activities(user)) if is_student(user) else queryset


def accessible_videos(user):
    queryset = Video.objects.select_related("activity", "media_asset", "thumbnail")
    return queryset.filter(activity__in=accessible_activities(user)) if is_student(user) else queryset


def accessible_experiments(user):
    queryset = Experiment.objects.select_related("activity")
    return queryset.filter(activity__in=accessible_activities(user)) if is_student(user) else queryset


def accessible_practice_sets(user):
    queryset = PracticeSet.objects.select_related("activity").prefetch_related("items__video")
    return queryset.filter(activity__in=accessible_activities(user)) if is_student(user) else queryset


def accessible_practice_items(user):
    queryset = PracticeItem.objects.select_related("practice_set__activity", "video")
    return queryset.filter(practice_set__in=accessible_practice_sets(user)) if is_student(user) else queryset
