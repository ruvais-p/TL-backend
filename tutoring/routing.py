from django.urls import path

from .consumers import CourseSupportConsumer


websocket_urlpatterns = [
    path("ws/course-support/", CourseSupportConsumer.as_asgi()),
]
