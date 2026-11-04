import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False
_PLACEHOLDER_MARKERS = ("change", "replace", "local-only", "dev-only", "insecure", "example")
if (
    not os.getenv("DJANGO_SECRET_KEY")
    or len(SECRET_KEY) < 50  # noqa: F405
    or len(set(SECRET_KEY)) < 5  # noqa: F405
    or any(marker in SECRET_KEY.lower() for marker in _PLACEHOLDER_MARKERS)  # noqa: F405
):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a strong, unique value of at least 50 characters.")
if MOODLE_SSO_SECRET and any(marker in MOODLE_SSO_SECRET.lower() for marker in _PLACEHOLDER_MARKERS):  # noqa: F405
    raise ImproperlyConfigured("MOODLE_SSO_SECRET is a placeholder; set a unique secret or leave it empty to disable Moodle SSO.")
if not os.getenv("PRIVATE_DOCUMENT_ROOT") and not os.getenv("ALLOW_EPHEMERAL_PRIVATE_DOCUMENTS"):
    raise ImproperlyConfigured("PRIVATE_DOCUMENT_ROOT must point at a persistent volume in production.")
if os.getenv("RAILWAY_ENVIRONMENT_ID"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "true").lower() == "true"
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,  # noqa: F405
        "KEY_PREFIX": "tella",
    },
}
