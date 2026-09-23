from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_auth0_configuration(app_configs, **kwargs):
    if not settings.AUTH0_ENABLED:
        return []

    errors = []
    required = {
        "AUTH0_ISSUER": settings.AUTH0_ISSUER,
        "AUTH0_AUDIENCE": settings.AUTH0_AUDIENCE,
        "AUTH0_EMAIL_CLAIM": settings.AUTH0_EMAIL_CLAIM,
        "AUTH0_EMAIL_VERIFIED_CLAIM": settings.AUTH0_EMAIL_VERIFIED_CLAIM,
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        errors.append(Error(
            f"Auth0 is enabled but required settings are empty: {', '.join(missing)}.",
            id="accounts.E001",
        ))
    if settings.AUTH0_ALGORITHM != "RS256":
        errors.append(Error(
            "AUTH0_ALGORITHM must be RS256.",
            id="accounts.E002",
        ))
    issuer = urlsplit(settings.AUTH0_ISSUER)
    if settings.AUTH0_ISSUER and (
        issuer.scheme != "https"
        or not issuer.netloc
        or issuer.username
        or issuer.password
        or issuer.path != "/"
        or issuer.query
        or issuer.fragment
    ):
        errors.append(Error(
            "AUTH0_ISSUER must be an absolute HTTPS tenant origin.",
            id="accounts.E004",
        ))
    if settings.AUTH0_JWKS_CACHE_SECONDS <= 0 or settings.AUTH0_HTTP_TIMEOUT_SECONDS <= 0:
        errors.append(Error(
            "Auth0 JWKS cache and HTTP timeout values must be positive.",
            id="accounts.E003",
        ))
    return errors
