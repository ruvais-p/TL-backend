import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator, OriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
django_asgi_application = get_asgi_application()

from django.conf import settings  # noqa: E402
from tutoring.middleware import SupportSocketTicketMiddleware  # noqa: E402
from tutoring.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_application,
    "websocket": AllowedHostsOriginValidator(
        OriginValidator(
            SupportSocketTicketMiddleware(URLRouter(websocket_urlpatterns)),
            settings.COURSE_SUPPORT_CHAT_ALLOWED_ORIGINS,
        )
    ),
})
