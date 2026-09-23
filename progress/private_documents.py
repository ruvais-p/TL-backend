import hashlib
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from progress.models import OpportunityApplicationDocument


MAX_RESUME_BYTES = 5 * 1024 * 1024
ALLOWED_RESUME_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)


class ResumeValidationError(Exception):
    pass


class ResumeAccessError(Exception):
    pass


def private_document_storage():
    return FileSystemStorage(location=settings.PRIVATE_DOCUMENT_ROOT)


def validate_resume(upload):
    if upload.size > MAX_RESUME_BYTES:
        raise ResumeValidationError("Resume files must be 5 MiB or smaller.")
    if upload.size <= 0:
        raise ResumeValidationError("Resume files cannot be empty.")
    if upload.content_type not in ALLOWED_RESUME_MIME_TYPES:
        raise ResumeValidationError("Upload a PDF, DOC, or DOCX resume.")


def store_resume(*, application, upload):
    validate_resume(upload)
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    storage_key = f"applications/{uuid4().hex}"
    storage = private_document_storage()
    saved_key = None
    try:
        saved_key = storage.save(storage_key, upload)
        return OpportunityApplicationDocument.objects.create(
            application=application,
            storage_key=saved_key,
            original_filename=Path(upload.name).name[:255],
            mime_type=upload.content_type,
            file_size=upload.size,
            checksum_sha256=digest.hexdigest(),
        )
    except Exception:
        if saved_key:
            storage.delete(saved_key)
        raise


def delete_resume(document):
    storage = private_document_storage()
    storage.delete(document.storage_key)
    document.delete()


def authorize_resume_download(*, document, user):
    if document.application.applicant_id == user.id:
        return
    if user.has_perm("progress.review_opportunityapplication") and user.has_perm(
        "progress.download_opportunityapplicationdocument"
    ):
        return
    raise ResumeAccessError("Resume not found.")


def open_resume(*, document, user):
    authorize_resume_download(document=document, user=user)
    return private_document_storage().open(document.storage_key, "rb")
