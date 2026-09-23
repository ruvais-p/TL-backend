import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class MathTutorProviderError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def ask_math_tutor(message: str) -> str:
    if not settings.MATH_TUTOR_API_KEY:
        raise MathTutorProviderError("provider_not_configured")

    request = Request(
        f"{settings.MATH_TUTOR_API_URL}/api/ask",
        data=json.dumps({"message": message}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": settings.MATH_TUTOR_API_KEY,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.MATH_TUTOR_TIMEOUT_SECONDS) as response:  # noqa: S310 - configured HTTPS endpoint
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise MathTutorProviderError("provider_authentication_failed" if exc.code in {401, 403} else "provider_http_error") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise MathTutorProviderError("provider_unavailable") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise MathTutorProviderError("provider_invalid_response") from exc

    if not isinstance(payload, dict) or payload.get("success") is not True or not isinstance(payload.get("reply"), str):
        raise MathTutorProviderError("provider_invalid_response")
    return payload["reply"]

