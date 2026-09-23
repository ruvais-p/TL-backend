from django.db.models import Prefetch
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Chapter, Course, CourseVersion, LearningActivity, Program, PublishStatus, Subtopic
from .permissions import CanManageCurriculum, CanPublishCurriculum
from .selectors import accessible_activities, accessible_chapters, accessible_courses, accessible_subtopics, course_structure_queryset, is_student
from .serializers import (
    ChapterSerializer, CourseSerializer, CourseVersionSerializer, DuplicateSerializer,
    LearningActivitySerializer, ProgramSerializer, ReorderSerializer, SubtopicSerializer,
)


class CurriculumModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanManageCurriculum]


class ProgramViewSet(CurriculumModelViewSet):
    queryset = Program.objects.all()
    serializer_class = ProgramSerializer

    def get_queryset(self):
        queryset = Program.objects.prefetch_related(Prefetch("courses", queryset=course_structure_queryset(self.request.user)))
        if is_student(self.request.user):
            queryset = queryset.filter(status=PublishStatus.PUBLISHED, courses__in=accessible_courses(self.request.user)).distinct()
        return queryset

    def perform_create(self, serializer):
        serializer.instance = services.create_program(actor=self.request.user, **serializer.validated_data)


class CourseViewSet(CurriculumModelViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer

    def get_queryset(self):
        return course_structure_queryset(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_course(actor=self.request.user, **serializer.validated_data)

    @action(detail=True, methods=["get"])
    def chapters(self, request, pk=None):
        course = self.get_object()
        chapters = accessible_chapters(request.user).filter(course_version__course=course)
        return Response(ChapterSerializer(chapters, many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, CanPublishCurriculum])
    def publish(self, request, pk=None):
        course = self.get_object()
        version = course.versions.filter(id=request.data.get("version_id")).first()
        if version is None:
            return Response({"error": {"code": "VERSION_NOT_FOUND", "message": "Course version not found.", "details": {}}}, status=400)
        services.publish_course_version(actor=request.user, version=version)
        return Response(self.get_serializer(self.get_queryset().get(pk=course.pk)).data)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        serializer = DuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data.get("code"):
            serializer.fail("required")
        clone = services.duplicate_course(actor=request.user, course=self.get_object(), **serializer.validated_data)
        return Response(self.get_serializer(clone).data, status=status.HTTP_201_CREATED)


class CourseVersionViewSet(CurriculumModelViewSet):
    queryset = CourseVersion.objects.select_related("course", "created_by").prefetch_related("chapters")
    serializer_class = CourseVersionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if is_student(self.request.user):
            queryset = queryset.filter(course__in=accessible_courses(self.request.user), status=PublishStatus.PUBLISHED)
        return queryset

    def perform_create(self, serializer):
        serializer.instance = services.create_course_version(actor=self.request.user, **serializer.validated_data)

    @action(detail=True, methods=["post"])
    def reorder_chapters(self, request, pk=None):
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_chapters(actor=request.user, course_version=self.get_object(), ordered_ids=serializer.validated_data["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChapterViewSet(CurriculumModelViewSet):
    queryset = Chapter.objects.all()
    serializer_class = ChapterSerializer

    def get_queryset(self):
        return accessible_chapters(self.request.user).prefetch_related("subtopics__activities")

    def perform_create(self, serializer):
        serializer.instance = services.create_chapter(actor=self.request.user, **serializer.validated_data)

    @action(detail=True, methods=["get"])
    def subtopics(self, request, pk=None):
        items = accessible_subtopics(request.user).filter(chapter=self.get_object()).prefetch_related("activities")
        return Response(SubtopicSerializer(items, many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def reorder_subtopics(self, request, pk=None):
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_subtopics(actor=request.user, chapter=self.get_object(), ordered_ids=serializer.validated_data["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubtopicViewSet(CurriculumModelViewSet):
    queryset = Subtopic.objects.all()
    serializer_class = SubtopicSerializer

    def get_queryset(self):
        return accessible_subtopics(self.request.user).prefetch_related("activities")

    def perform_create(self, serializer):
        serializer.instance = services.create_subtopic(actor=self.request.user, **serializer.validated_data)

    @action(detail=True, methods=["get"])
    def activities(self, request, pk=None):
        items = accessible_activities(request.user).filter(subtopic=self.get_object())
        return Response(LearningActivitySerializer(items, many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def reorder_activities(self, request, pk=None):
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_activities(actor=request.user, subtopic=self.get_object(), ordered_ids=serializer.validated_data["ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivityViewSet(CurriculumModelViewSet):
    queryset = LearningActivity.objects.all()
    serializer_class = LearningActivitySerializer

    def get_queryset(self):
        return accessible_activities(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_activity(actor=self.request.user, **serializer.validated_data)

    @action(detail=True, methods=["get"], url_path="workshop")
    def workshop(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)
