from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import ActivityContent, Experiment, PracticeItem, PracticeSet, Video
from .permissions import CanManageContent
from .selectors import accessible_content, accessible_experiments, accessible_practice_items, accessible_practice_sets, accessible_videos
from .serializers import (
    ActivityContentSerializer, ExperimentSerializer, PracticeItemSerializer,
    PracticeSetSerializer, ReorderPracticeItemsSerializer, VideoSerializer,
)


class ContentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, CanManageContent]


class ActivityContentViewSet(ContentViewSet):
    queryset = ActivityContent.objects.all()
    serializer_class = ActivityContentSerializer

    def get_queryset(self):
        return accessible_content(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_activity_content(actor=self.request.user, **serializer.validated_data)


class VideoViewSet(ContentViewSet):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer

    def get_queryset(self):
        return accessible_videos(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_video(actor=self.request.user, **serializer.validated_data)


class ExperimentViewSet(ContentViewSet):
    queryset = Experiment.objects.all()
    serializer_class = ExperimentSerializer

    def get_queryset(self):
        return accessible_experiments(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_experiment(actor=self.request.user, **serializer.validated_data)


class PracticeSetViewSet(ContentViewSet):
    queryset = PracticeSet.objects.all()
    serializer_class = PracticeSetSerializer

    def get_queryset(self):
        return accessible_practice_sets(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_practice_set(actor=self.request.user, **serializer.validated_data)

    @action(detail=True, methods=["post"])
    def reorder_items(self, request, pk=None):
        serializer = ReorderPracticeItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_practice_items(
            actor=request.user, practice_set=self.get_object(), ordered_ids=serializer.validated_data["ids"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PracticeItemViewSet(ContentViewSet):
    queryset = PracticeItem.objects.all()
    serializer_class = PracticeItemSerializer

    def get_queryset(self):
        return accessible_practice_items(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_practice_item(actor=self.request.user, **serializer.validated_data)
