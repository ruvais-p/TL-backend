from .base import *  # noqa: F403

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Local development runs a single ASGI process, so it should not require a
# separately managed Redis instance for real-time course-support messages.
# Production overrides the cache and continues to use the Redis channel layer
# configured in base settings.
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}
