from collections import defaultdict

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.constants import GroupName
from accounts.permissions import active_permission_queryset


PERMISSIONS_BY_GROUP = {
    GroupName.ADMIN: {
        "accounts.add_user", "accounts.change_user", "accounts.view_user",
        "accounts.manage_users", "accounts.bulk_import_students",
        "curriculum.view_program", "curriculum.view_course", "curriculum.view_courseversion",
        "curriculum.view_chapter", "curriculum.view_subtopic", "curriculum.view_learningactivity",
        "curriculum.add_learningactivity", "curriculum.change_learningactivity",
        "progress.view_activityprogress",
        "progress.view_all_student_progress", "progress.view_assigned_student_progress",
        "progress.add_careeropportunity", "progress.change_careeropportunity", "progress.view_careeropportunity",
        "progress.change_opportunityapplication", "progress.view_opportunityapplication",
        "progress.review_opportunityapplication", "progress.download_opportunityapplicationdocument",
        "students.add_studentgroup", "students.change_studentgroup", "students.view_studentgroup",
        "students.add_studentgroupmember", "students.change_studentgroupmember", "students.delete_studentgroupmember", "students.view_studentgroupmember",
        "students.add_enrollment", "students.change_enrollment", "students.view_enrollment",
        "students.add_courseassignment", "students.change_courseassignment", "students.view_courseassignment",
        "students.add_externalusermapping", "students.change_externalusermapping", "students.view_externalusermapping",
        "students.manage_students", "students.manage_student_groups", "students.assign_course",
        "assessments.add_question", "assessments.change_question", "assessments.delete_question", "assessments.view_question",
        "assessments.add_questionoption", "assessments.change_questionoption", "assessments.view_questionoption",
        "assessments.add_casestudy", "assessments.change_casestudy", "assessments.view_casestudy",
        "assessments.add_casestudyquestion", "assessments.change_casestudyquestion", "assessments.view_casestudyquestion",
        "assessments.add_learningcheck", "assessments.change_learningcheck", "assessments.view_learningcheck",
        "assessments.add_learningcheckquestion", "assessments.change_learningcheckquestion", "assessments.view_learningcheckquestion",
        "assessments.view_assessmentattempt", "assessments.view_assessmentanswer", "assessments.grade_assessment",
        "content.add_activitycontent", "content.change_activitycontent", "content.view_activitycontent",
        "content.add_video", "content.change_video", "content.view_video",
        "content.add_experiment", "content.change_experiment", "content.view_experiment",
        "content.add_practiceset", "content.change_practiceset", "content.view_practiceset",
        "content.add_practiceitem", "content.change_practiceitem", "content.view_practiceitem",
        "media_library.add_mediaasset", "media_library.change_mediaasset", "media_library.view_mediaasset",
        "students.view_studentgroup", "students.view_studentgroupmember", "students.view_enrollment", "students.view_courseassignment",
    },
    GroupName.ACADEMIC_MANAGER: {
        "curriculum.add_program", "curriculum.change_program", "curriculum.view_program",
        "curriculum.add_course", "curriculum.change_course", "curriculum.view_course",
        "curriculum.add_courseversion", "curriculum.change_courseversion", "curriculum.view_courseversion",
        "curriculum.add_chapter", "curriculum.change_chapter", "curriculum.view_chapter",
        "curriculum.add_subtopic", "curriculum.change_subtopic", "curriculum.view_subtopic",
        "curriculum.add_learningactivity", "curriculum.change_learningactivity", "curriculum.view_learningactivity",
        "curriculum.publish_course", "curriculum.archive_course", "curriculum.duplicate_course",
        "curriculum.publish_chapter", "curriculum.duplicate_chapter",
        "progress.view_activityprogress",
        "progress.view_all_student_progress",
        "assessments.add_question", "assessments.change_question", "assessments.view_question",
        "assessments.add_questionoption", "assessments.change_questionoption", "assessments.view_questionoption",
        "assessments.add_casestudy", "assessments.change_casestudy", "assessments.view_casestudy",
        "assessments.add_casestudyquestion", "assessments.change_casestudyquestion", "assessments.view_casestudyquestion",
        "assessments.add_learningcheck", "assessments.change_learningcheck", "assessments.view_learningcheck",
        "assessments.add_learningcheckquestion", "assessments.change_learningcheckquestion", "assessments.view_learningcheckquestion",
        "assessments.view_assessmentattempt", "assessments.view_assessmentanswer", "assessments.grade_assessment",
        "content.add_activitycontent", "content.change_activitycontent", "content.view_activitycontent",
        "content.add_video", "content.change_video", "content.view_video",
        "content.add_experiment", "content.change_experiment", "content.view_experiment",
        "content.add_practiceset", "content.change_practiceset", "content.view_practiceset",
        "content.add_practiceitem", "content.change_practiceitem", "content.view_practiceitem",
        "media_library.add_mediaasset", "media_library.change_mediaasset", "media_library.view_mediaasset",
        "tutoring.manage_course_chatbot",
        "tutoring.reply_to_assigned_course_support_chats",
        "tutoring.view_all_course_support_chats",
        "tutoring.close_course_support_chats",
    },
    GroupName.CONTENT_MANAGER: {
        "curriculum.view_program", "curriculum.view_course", "curriculum.view_courseversion",
        "curriculum.view_chapter", "curriculum.change_chapter",
        "curriculum.view_subtopic", "curriculum.change_subtopic",
        "curriculum.add_learningactivity", "curriculum.change_learningactivity", "curriculum.view_learningactivity",
        "content.add_activitycontent", "content.change_activitycontent", "content.view_activitycontent",
        "content.add_video", "content.change_video", "content.view_video",
        "content.add_experiment", "content.change_experiment", "content.view_experiment",
        "content.add_practiceset", "content.change_practiceset", "content.view_practiceset",
        "content.add_practiceitem", "content.change_practiceitem", "content.view_practiceitem",
        "media_library.add_mediaasset", "media_library.change_mediaasset", "media_library.view_mediaasset",
        "tutoring.manage_course_chatbot",
    },
    GroupName.TEACHER: {
        "accounts.view_user", "curriculum.view_course", "curriculum.view_courseversion",
        "curriculum.view_chapter", "curriculum.view_subtopic", "curriculum.view_learningactivity",
        "progress.view_activityprogress",
        "progress.view_assigned_student_progress",
        "assessments.view_learningcheck", "assessments.view_learningcheckquestion", "assessments.view_assessmentattempt", "assessments.view_assessmentanswer",
        "content.view_activitycontent", "content.view_video", "content.view_experiment",
        "content.view_practiceset", "content.view_practiceitem", "media_library.view_mediaasset",
        "students.view_studentgroup", "students.view_studentgroupmember", "students.view_enrollment", "students.view_courseassignment",
        "tutoring.reply_to_assigned_course_support_chats", "tutoring.close_course_support_chats",
    },
    GroupName.STUDENT: {
        "accounts.view_user", "curriculum.view_course", "curriculum.view_courseversion",
        "curriculum.view_chapter", "curriculum.view_subtopic", "curriculum.view_learningactivity",
        "progress.add_activityprogress", "progress.change_activityprogress", "progress.view_activityprogress",
        "content.view_activitycontent", "content.view_video", "content.view_experiment",
        "content.view_practiceset", "content.view_practiceitem", "media_library.view_mediaasset",
        "students.view_studentgroup", "students.view_studentgroupmember", "students.view_enrollment",
        "students.view_courseassignment", "students.view_externalusermapping",
        "assessments.view_learningcheck",
    },
}


class Command(BaseCommand):
    help = "Create Django Groups and synchronize their permissions idempotently."

    @transaction.atomic
    def handle(self, *args, **options):
        all_permissions = active_permission_queryset().select_related("content_type")
        permission_map = {
            f"{permission.content_type.app_label}.{permission.codename}": permission
            for permission in all_permissions
        }
        missing = defaultdict(list)
        for name in GroupName.values:
            group, _ = Group.objects.get_or_create(name=name)
            requested = set(permission_map) if name == GroupName.SUPER_ADMIN else PERMISSIONS_BY_GROUP[name]
            resolved = [permission_map[key] for key in requested if key in permission_map]
            missing[name].extend(sorted(requested - permission_map.keys()))
            group.permissions.set(resolved)
            self.stdout.write(self.style.SUCCESS(f"[OK] {name}"))
            self.stdout.write(f"  {len(resolved)} permissions")
        for name, keys in missing.items():
            if keys:
                self.stdout.write(self.style.WARNING(f"  {name}: skipped unavailable future permissions: {', '.join(keys)}"))
