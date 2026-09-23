import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure")
DEBUG = False
ALLOWED_HOSTS = [
    value.strip()
    for value in os.getenv("DJANGO_ALLOWED_HOSTS", os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1")).split(",")
    if value.strip()
]

INSTALLED_APPS = [
    "daphne", "django.contrib.auth", "django.contrib.contenttypes",
    "rest_framework", "rest_framework_simplejwt.token_blacklist", "corsheaders",
    "accounts", "media_library", "curriculum", "content", "students", "assessments", "workshops", "progress", "tutoring",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.getenv("POSTGRES_DB", "tella_dev"),
    "USER": os.getenv("POSTGRES_USER", "tella"),
    "PASSWORD": os.getenv("POSTGRES_PASSWORD", "tella_dev_local"),
    "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
    "PORT": os.getenv("POSTGRES_PORT", "5432"),
    "CONN_MAX_AGE": int(os.getenv("POSTGRES_CONN_MAX_AGE", "60")),
}}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_DOCUMENT_ROOT = Path(
    os.getenv("PRIVATE_DOCUMENT_ROOT", BASE_DIR / "private_documents")
)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MOODLE_ORIGIN = os.getenv("MOODLE_ORIGIN", "http://localhost:8080")
MOODLE_SSO_SECRET = os.getenv("MOODLE_SSO_SECRET", "")
AUTH0_ENABLED = os.getenv("AUTH0_ENABLED", "false").strip().lower() == "true"
AUTH0_ISSUER = os.getenv("AUTH0_ISSUER", "").strip().rstrip("/")
if AUTH0_ISSUER:
    AUTH0_ISSUER += "/"
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "").strip()
AUTH0_ALGORITHM = os.getenv("AUTH0_ALGORITHM", "RS256").strip()
AUTH0_EMAIL_CLAIM = os.getenv("AUTH0_EMAIL_CLAIM", "https://tella.systems/email").strip()
AUTH0_EMAIL_VERIFIED_CLAIM = os.getenv(
    "AUTH0_EMAIL_VERIFIED_CLAIM", "https://tella.systems/email_verified"
).strip()
AUTH0_JWKS_CACHE_SECONDS = int(os.getenv("AUTH0_JWKS_CACHE_SECONDS", "300"))
AUTH0_HTTP_TIMEOUT_SECONDS = float(os.getenv("AUTH0_HTTP_TIMEOUT_SECONDS", "5"))
CORS_ALLOWED_ORIGINS = [v.strip() for v in os.getenv("CORS_ALLOWED_ORIGINS", MOODLE_ORIGIN).split(",") if v.strip()]
CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)

COURSE_SUPPORT_CHAT_ENABLED = os.getenv("COURSE_SUPPORT_CHAT_ENABLED", "false").strip().lower() == "true"
COURSE_SUPPORT_CHAT_MESSAGE_MAX_CHARS = int(os.getenv("COURSE_SUPPORT_CHAT_MESSAGE_MAX_CHARS", "2000"))
COURSE_SUPPORT_CHAT_EVENT_MAX_BYTES = int(os.getenv("COURSE_SUPPORT_CHAT_EVENT_MAX_BYTES", "65536"))
COURSE_SUPPORT_CHAT_HISTORY_PAGE_SIZE = int(os.getenv("COURSE_SUPPORT_CHAT_HISTORY_PAGE_SIZE", "50"))
COURSE_SUPPORT_CHAT_SEND_RATE = os.getenv("COURSE_SUPPORT_CHAT_SEND_RATE", "20/min")
COURSE_SUPPORT_CHAT_CONNECTION_RATE = os.getenv("COURSE_SUPPORT_CHAT_CONNECTION_RATE", "10/min")
COURSE_SUPPORT_CHAT_MAX_CONNECTIONS_PER_USER = int(os.getenv("COURSE_SUPPORT_CHAT_MAX_CONNECTIONS_PER_USER", "5"))
COURSE_SUPPORT_CHAT_TICKET_TTL_SECONDS = int(os.getenv("COURSE_SUPPORT_CHAT_TICKET_TTL_SECONDS", "30"))
COURSE_SUPPORT_CHAT_RETENTION_DAYS = int(os.getenv("COURSE_SUPPORT_CHAT_RETENTION_DAYS", "365"))
COURSE_SUPPORT_CHAT_TICKET_CLEANUP_HOURS = int(os.getenv("COURSE_SUPPORT_CHAT_TICKET_CLEANUP_HOURS", "1"))
COURSE_SUPPORT_CHAT_WEBSOCKET_URL = os.getenv(
    "COURSE_SUPPORT_CHAT_WEBSOCKET_URL",
    "ws://127.0.0.1:8000/ws/course-support/",
).strip()
COURSE_SUPPORT_CHAT_ALLOWED_ORIGINS = [
    value.strip().rstrip("/")
    for value in os.getenv("COURSE_SUPPORT_CHAT_ALLOWED_ORIGINS", ",".join(CORS_ALLOWED_ORIGINS)).split(",")
    if value.strip()
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
        "auth0_exchange": os.getenv("AUTH0_EXCHANGE_THROTTLE_RATE", "10/min"),
        "course_chat": os.getenv("COURSE_CHAT_THROTTLE_RATE", "10/min"),
        "course_support_send": COURSE_SUPPORT_CHAT_SEND_RATE,
        "course_support_connection": COURSE_SUPPORT_CHAT_CONNECTION_RATE,
    },
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "tella-default",
}}
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "prefix": "tella-course-support",
        },
    },
}

MATH_TUTOR_API_URL = os.getenv(
    "MATH_TUTOR_API_URL", "https://math-tutor-api-938810058241.europe-west3.run.app"
).rstrip("/")
MATH_TUTOR_API_KEY = os.getenv("MATH_TUTOR_API_KEY", "")
MATH_TUTOR_TIMEOUT_SECONDS = float(os.getenv("MATH_TUTOR_TIMEOUT_SECONDS", "15"))
COURSE_CHAT_MESSAGE_MAX_CHARS = int(os.getenv("COURSE_CHAT_MESSAGE_MAX_CHARS", "1000"))
COURSE_CHAT_CONTEXT_MAX_CHARS = int(os.getenv("COURSE_CHAT_CONTEXT_MAX_CHARS", "24000"))
COURSE_CHAT_PROVIDER_MAX_CHARS = int(os.getenv("COURSE_CHAT_PROVIDER_MAX_CHARS", "30000"))
COURSE_CHAT_HISTORY_MESSAGES = int(os.getenv("COURSE_CHAT_HISTORY_MESSAGES", "8"))
COURSE_CHAT_MAX_CHUNKS = int(os.getenv("COURSE_CHAT_MAX_CHUNKS", "24"))
COURSE_CHAT_RETENTION_DAYS = int(os.getenv("COURSE_CHAT_RETENTION_DAYS", "30"))
COURSE_CHAT_REFUSAL = os.getenv(
    "COURSE_CHAT_REFUSAL", "I can only answer questions covered by this course."
)
