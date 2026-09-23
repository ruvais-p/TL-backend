import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from jwt import PyJWKClient

from .managers import normalize_email_address
from .models import Auth0Identity, User

logger = logging.getLogger("accounts.auth0")


class Auth0VerificationError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class Auth0AdmissionError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Auth0Claims:
    issuer: str
    subject: str
    email: str
    email_verified: bool


def _security_event(event: str, *, reason: str, correlation_id: str, user_id=None):
    logger.info(
        "auth0_exchange event=%s reason=%s correlation_id=%s user_id=%s",
        event,
        reason,
        correlation_id,
        str(user_id) if user_id else "",
    )


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str, cache_seconds: int, timeout_seconds: float):
    return PyJWKClient(
        jwks_url,
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=cache_seconds,
        timeout=timeout_seconds,
    )


def verify_auth0_assertion(assertion: str, *, jwks_client=None) -> Auth0Claims:
    if not settings.AUTH0_ENABLED:
        raise Auth0VerificationError("disabled")
    if not assertion or not isinstance(assertion, str):
        raise Auth0VerificationError("missing_assertion")
    try:
        header = jwt.get_unverified_header(assertion)
        if header.get("alg") != settings.AUTH0_ALGORITHM:
            raise Auth0VerificationError("unsupported_algorithm")
        client = jwks_client or _jwks_client(
            f"{settings.AUTH0_ISSUER}.well-known/jwks.json",
            settings.AUTH0_JWKS_CACHE_SECONDS,
            settings.AUTH0_HTTP_TIMEOUT_SECONDS,
        )
        key = client.get_signing_key_from_jwt(assertion).key
        payload = jwt.decode(
            assertion,
            key,
            algorithms=[settings.AUTH0_ALGORITHM],
            audience=settings.AUTH0_AUDIENCE,
            issuer=settings.AUTH0_ISSUER,
            options={"require": ["aud", "exp", "iat", "iss", "sub"]},
        )
    except Auth0VerificationError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise Auth0VerificationError("expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise Auth0VerificationError("wrong_issuer") from exc
    except jwt.InvalidAudienceError as exc:
        raise Auth0VerificationError("wrong_audience") from exc
    except (jwt.PyJWTError, OSError, ValueError) as exc:
        raise Auth0VerificationError("invalid_assertion") from exc

    subject = payload.get("sub")
    email = payload.get(settings.AUTH0_EMAIL_CLAIM)
    email_verified = payload.get(settings.AUTH0_EMAIL_VERIFIED_CLAIM)
    if not isinstance(subject, str) or not subject.strip():
        raise Auth0VerificationError("missing_subject")
    if not isinstance(email, str) or not email.strip():
        raise Auth0VerificationError("missing_email")
    if not isinstance(email_verified, bool):
        raise Auth0VerificationError("missing_email_verification")
    return Auth0Claims(
        issuer=settings.AUTH0_ISSUER,
        subject=subject.strip(),
        email=normalize_email_address(email),
        email_verified=email_verified,
    )


@transaction.atomic
def resolve_auth0_identity(claims: Auth0Claims, *, correlation_id: str | None = None):
    correlation_id = correlation_id or str(uuid.uuid4())
    normalized_email = normalize_email_address(claims.email)
    identity = Auth0Identity.objects.select_for_update().select_related("user").filter(
        issuer=claims.issuer,
        subject=claims.subject,
    ).first()
    if identity:
        if not identity.user.is_active:
            _security_event("denied", reason="inactive", correlation_id=correlation_id, user_id=identity.user_id)
            raise Auth0AdmissionError("inactive")
        identity.last_authenticated_at = timezone.now()
        identity.save(update_fields=["last_authenticated_at"])
        _security_event("resolved", reason="existing_link", correlation_id=correlation_id, user_id=identity.user_id)
        return identity.user

    if not claims.email_verified:
        _security_event("denied", reason="unverified_email", correlation_id=correlation_id)
        raise Auth0AdmissionError("unverified_email")

    users = list(User.objects.select_for_update().filter(email__iexact=normalized_email)[:2])
    if len(users) != 1:
        reason = "unknown_email" if not users else "ambiguous_email"
        _security_event("denied", reason=reason, correlation_id=correlation_id)
        raise Auth0AdmissionError(reason)
    user = users[0]
    if not user.is_active:
        _security_event("denied", reason="inactive", correlation_id=correlation_id, user_id=user.pk)
        raise Auth0AdmissionError("inactive")

    try:
        with transaction.atomic():
            identity = Auth0Identity.objects.create(
                user=user,
                issuer=claims.issuer,
                subject=claims.subject,
                email_at_link_time=normalized_email,
                last_authenticated_at=timezone.now(),
            )
    except IntegrityError:
        identity = Auth0Identity.objects.select_for_update().select_related("user").filter(
            issuer=claims.issuer,
            subject=claims.subject,
        ).first()
        if identity is None or identity.user_id != user.pk:
            _security_event("denied", reason="link_conflict", correlation_id=correlation_id, user_id=user.pk)
            raise Auth0AdmissionError("link_conflict")
        user = identity.user
    _security_event("linked", reason="verified_email", correlation_id=correlation_id, user_id=user.pk)
    return user


def exchange_auth0_assertion(assertion: str, *, correlation_id: str | None = None, jwks_client=None):
    correlation_id = correlation_id or str(uuid.uuid4())
    try:
        claims = verify_auth0_assertion(assertion, jwks_client=jwks_client)
    except Auth0VerificationError as exc:
        _security_event("denied", reason=exc.reason, correlation_id=correlation_id)
        raise
    return resolve_auth0_identity(claims, correlation_id=correlation_id)
