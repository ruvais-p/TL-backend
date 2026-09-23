from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import HasModelPermission

from .models import WorkshopConfig, WorkshopModel
from .serializers import (
    StaffWorkshopModelSerializer, WorkshopConfigSerializer,
    WorkshopModelSerializer,
)


class WorkshopModelViewSet(viewsets.ModelViewSet):
    serializer_class = WorkshopModelSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = WorkshopModel.objects.filter(user=self.request.user)
        activity = self.request.query_params.get("activity")
        if activity:
            qs = qs.filter(activity_id=activity)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class WorkshopConfigViewSet(viewsets.ModelViewSet):
    queryset = WorkshopConfig.objects.select_related("activity")
    serializer_class = WorkshopConfigSerializer
    permission_classes = [IsAuthenticated, HasModelPermission]


class StaffWorkshopModelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkshopModel.objects.select_related("user", "activity")
    serializer_class = StaffWorkshopModelSerializer
    permission_classes = [IsAuthenticated, HasModelPermission]
