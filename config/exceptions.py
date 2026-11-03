from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def _messages(error: DjangoValidationError):
    if hasattr(error, "message_dict"):
        return error.message_dict
    return {"detail": error.messages[0] if len(error.messages) == 1 else error.messages}


def api_exception_handler(exc, context):
    """Map domain errors raised by services to 4xx instead of opaque 500s."""
    response = exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, DjangoValidationError):
        return Response(_messages(exc), status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, ObjectDoesNotExist):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, ProtectedError):
        return Response(
            {"detail": "This record is still in use by other records and cannot be deleted."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "This change conflicts with an existing record. Refresh and try again."},
            status=status.HTTP_409_CONFLICT,
        )
    return None
