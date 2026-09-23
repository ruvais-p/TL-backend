from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from curriculum.selectors import accessible_activities, accessible_courses, is_student

from .models import MediaAsset
from .permissions import CanManageMedia
from .serializers import MediaAssetSerializer
from .services import create_media_asset, create_uploaded_media_asset


class MediaAssetViewSet(viewsets.ModelViewSet):
    queryset = MediaAsset.objects.select_related("uploaded_by")
    serializer_class = MediaAssetSerializer
    permission_classes = [IsAuthenticated, CanManageMedia]

    def get_queryset(self):
        queryset = self.queryset
        if is_student(self.request.user):
            queryset = queryset.filter(
                Q(videos__activity__in=accessible_activities(self.request.user))
                | Q(video_thumbnails__activity__in=accessible_activities(self.request.user))
                | Q(course_thumbnails__in=accessible_courses(self.request.user))
            ).distinct()
        return queryset

    def perform_create(self, serializer):
        data = dict(serializer.validated_data)
        uploaded_file = data.pop("upload", None)
        if uploaded_file:
            serializer.instance = create_uploaded_media_asset(
                actor=self.request.user, uploaded_file=uploaded_file, **data
            )
        else:
            serializer.instance = create_media_asset(actor=self.request.user, **data)
