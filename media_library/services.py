import mimetypes
import uuid
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename

from .models import MediaAsset


def create_media_asset(*, actor, **data) -> MediaAsset:
    if not actor.has_perm("media_library.add_mediaasset"):
        raise PermissionDenied("You cannot create media assets.")
    return MediaAsset.objects.create(uploaded_by=actor, **data)


def store_media_upload(uploaded_file) -> dict:
    """Store an uploaded file and return model metadata without coupling callers to storage."""
    original_name = Path(uploaded_file.name or "upload.bin").name
    safe_name = get_valid_filename(original_name) or "upload.bin"
    storage_path = default_storage.save(f"uploads/{uuid.uuid4()}/{safe_name}", uploaded_file)
    mime_type = getattr(uploaded_file, "content_type", "") or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    major_type = mime_type.partition("/")[0].upper()
    return {
        "file_name": original_name,
        "file_type": major_type if major_type in {"VIDEO", "AUDIO", "IMAGE"} else "DOCUMENT",
        "mime_type": mime_type,
        "file_size": uploaded_file.size,
        "storage_path": storage_path,
        "status": MediaAsset.Status.READY,
    }


def create_uploaded_media_asset(*, actor, uploaded_file, **data) -> MediaAsset:
    stored = store_media_upload(uploaded_file)
    # Properties derived from the actual upload are authoritative. In particular,
    # never let multipart metadata point the database at a different storage path
    # (which would also leave the real upload orphaned on failure).
    stored.update({
        key: data[key]
        for key in ("duration_seconds",)
        if data.get(key) not in (None, "")
    })
    try:
        return create_media_asset(actor=actor, **stored)
    except Exception:
        default_storage.delete(stored["storage_path"])
        raise
