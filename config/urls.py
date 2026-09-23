from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from curriculum.views import (
    ActivityViewSet, ChapterViewSet, CourseVersionViewSet, CourseViewSet,
    ProgramViewSet, SubtopicViewSet,
)
from content.views import ActivityContentViewSet, ExperimentViewSet, PracticeItemViewSet, PracticeSetViewSet, VideoViewSet
from media_library.views import MediaAssetViewSet
from progress.views import ActivityProgressActionView, CareerOpportunityApplicationCreateView, CareerOpportunityDetailView, CareerOpportunityListView, GamificationMeView, LearnerApplicationListView, LearnerApplicationResumeView, LearnerApplicationWithdrawView, ProgressUpsertView
from progress.views import (
    ActivityProgressStaffViewSet, BadgeAwardStaffViewSet,
    CareerOpportunityStaffViewSet, LegacyAssessmentAttemptStaffViewSet,
    OpportunityApplicationStaffViewSet, PointEventStaffViewSet,
)
from progress.progress_views import MyActivityProgressListView, MyActivityProgressView, MyChapterProgressView, MyCourseProgressView, MyProgressView
from assessments.views import (
    AssessmentAnswerStaffViewSet, AssessmentAttemptStaffViewSet,
    CaseStudyQuestionViewSet, CaseStudyViewSet, LearningCheckQuestionViewSet,
    LearningCheckViewSet, QuestionOptionViewSet, QuestionViewSet,
)
from students.views import (
    CourseAssignmentViewSet, EnrollmentViewSet, ExternalUserMappingViewSet,
    StudentGroupMemberViewSet, StudentGroupViewSet, StudentViewSet, TeacherViewSet,
)
from workshops.views import (
    StaffWorkshopModelViewSet, WorkshopConfigViewSet, WorkshopModelViewSet,
)
from tutoring.views import (
    CourseChatView,
    CourseChatbotConfigViewSet,
    LearnerSupportConversationView,
    StaffSupportConversationListView,
    SupportConversationCloseView,
    SupportConversationMessagesView,
    SupportConversationReadView,
    SupportSocketTicketView,
)

router = DefaultRouter()
router.register(r"programs", ProgramViewSet, basename="program")
router.register(r"courses", CourseViewSet, basename="course")
router.register(r"course-versions", CourseVersionViewSet, basename="course-version")
router.register(r"chapters", ChapterViewSet, basename="chapter")
router.register(r"subtopics", SubtopicViewSet, basename="subtopic")
router.register(r"activities", ActivityViewSet, basename="activity")
router.register(r"activity-content", ActivityContentViewSet, basename="activity-content")
router.register(r"videos", VideoViewSet, basename="video")
router.register(r"experiments", ExperimentViewSet, basename="experiment")
router.register(r"practice-sets", PracticeSetViewSet, basename="practice-set")
router.register(r"practice-items", PracticeItemViewSet, basename="practice-item")
router.register(r"media-assets", MediaAssetViewSet, basename="media-asset")
router.register(r"students", StudentViewSet, basename="student")
router.register(r"teachers", TeacherViewSet, basename="teacher")
router.register(r"student-groups", StudentGroupViewSet, basename="student-group")
router.register(r"student-group-members", StudentGroupMemberViewSet, basename="student-group-member")
router.register(r"enrollments", EnrollmentViewSet, basename="enrollment")
router.register(r"course-assignments", CourseAssignmentViewSet, basename="course-assignment")
router.register(r"external-user-mappings", ExternalUserMappingViewSet, basename="external-user-mapping")
router.register(r"questions", QuestionViewSet, basename="question")
router.register(r"question-options", QuestionOptionViewSet, basename="question-option")
router.register(r"case-studies", CaseStudyViewSet, basename="case-study")
router.register(r"case-study-questions", CaseStudyQuestionViewSet, basename="case-study-question")
router.register(r"learning-checks", LearningCheckViewSet, basename="learning-check")
router.register(r"learning-check-questions", LearningCheckQuestionViewSet, basename="learning-check-question")
router.register(r"workshop-models", WorkshopModelViewSet, basename="workshop-model")
router.register(r"activity-progress-records", ActivityProgressStaffViewSet, basename="activity-progress-record")
router.register(r"assessment-attempts", AssessmentAttemptStaffViewSet, basename="assessment-attempt")
router.register(r"assessment-answers", AssessmentAnswerStaffViewSet, basename="assessment-answer")
router.register(r"point-events", PointEventStaffViewSet, basename="point-event")
router.register(r"badge-awards", BadgeAwardStaffViewSet, basename="badge-award")
router.register(r"career-opportunities", CareerOpportunityStaffViewSet, basename="career-opportunity")
router.register(r"opportunity-applications", OpportunityApplicationStaffViewSet, basename="opportunity-application")
router.register(r"legacy-assessment-attempts", LegacyAssessmentAttemptStaffViewSet, basename="legacy-assessment-attempt")
router.register(r"workshop-configs", WorkshopConfigViewSet, basename="workshop-config")
router.register(r"staff-workshop-models", StaffWorkshopModelViewSet, basename="staff-workshop-model")
router.register(r"course-chatbot-configs", CourseChatbotConfigViewSet, basename="course-chatbot-config")

urlpatterns = [
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/", include(router.urls)),
    path("api/v1/progress/", ProgressUpsertView.as_view(), name="progress_upsert"),
    path("api/v1/activities/<uuid:activity_id>/<str:action>/", ActivityProgressActionView.as_view(), name="activity_progress_action"),
    path("api/v1/me/progress/", MyProgressView.as_view(), name="my_progress"),
    path("api/v1/me/activity-progress/", MyActivityProgressListView.as_view(), name="my_activity_progress_list"),
    path("api/v1/me/courses/<uuid:course_id>/progress/", MyCourseProgressView.as_view(), name="my_course_progress"),
    path("api/v1/me/chapters/<uuid:chapter_id>/progress/", MyChapterProgressView.as_view(), name="my_chapter_progress"),
    path("api/v1/me/activities/<uuid:activity_id>/progress/", MyActivityProgressView.as_view(), name="my_activity_progress"),
    path("api/v1/gamification/me/", GamificationMeView.as_view(), name="gamification_me"),
    path("api/v1/career/opportunities/", CareerOpportunityListView.as_view(), name="career"),
    path("api/v1/career/opportunities/<uuid:opportunity_id>/", CareerOpportunityDetailView.as_view(), name="career-detail"),
    path("api/v1/career/opportunities/<uuid:opportunity_id>/applications/", CareerOpportunityApplicationCreateView.as_view(), name="career-apply"),
    path("api/v1/career/applications/me/", LearnerApplicationListView.as_view(), name="career-applications-me"),
    path("api/v1/career/applications/<uuid:application_id>/withdraw/", LearnerApplicationWithdrawView.as_view(), name="career-application-withdraw"),
    path("api/v1/career/applications/<uuid:application_id>/resume/", LearnerApplicationResumeView.as_view(), name="career-application-resume"),
    path("api/v1/courses/<uuid:course_id>/chat/", CourseChatView.as_view(), name="course-chat"),
    path("api/v1/courses/<uuid:course_id>/support-conversation/", LearnerSupportConversationView.as_view(), name="course-support-conversation"),
    path("api/v1/course-support/conversations/", StaffSupportConversationListView.as_view(), name="course-support-conversations"),
    path("api/v1/course-support/conversations/<uuid:conversation_id>/messages/", SupportConversationMessagesView.as_view(), name="course-support-messages"),
    path("api/v1/course-support/conversations/<uuid:conversation_id>/read/", SupportConversationReadView.as_view(), name="course-support-read"),
    path("api/v1/course-support/conversations/<uuid:conversation_id>/close/", SupportConversationCloseView.as_view(), name="course-support-close"),
    path("api/v1/course-support/socket-ticket/", SupportSocketTicketView.as_view(), name="course-support-socket-ticket"),
    path("api/v1/health/", lambda request: JsonResponse({"ok": True})),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
