"""Local-disk file upload support (Employee photo).

Every other "reference" field in this codebase (photo_reference,
residence_proof_reference, Asset attachments) has, until now, stored only a
manually-typed URL/filename — every docstring pointing at one says "no file
upload/storage infrastructure exists yet". This module is that
infrastructure: it validates, safely stores, and returns a servable URL for
an uploaded file. Scoped to Employee photos for now (the one place asked
for), but the validate/save split below is written to be reused by a future
Asset-attachment upload without duplicating the security-sensitive parts.

Security notes (this handles untrusted, user-supplied file content):
- The client's `Content-Type` header and original filename are both
  attacker-controlled and are never trusted for the *type* decision — the
  first bytes of the file itself (its magic number) decide what it really
  is. A client can rename a script to "photo.jpg"; it cannot fake the PNG
  signature and also be a valid PNG.
- The saved filename is always a freshly generated UUID, never derived from
  the client's filename — the client's filename is never used to build a
  filesystem path, so there is no path-traversal surface from it at all.
- The file is read in chunks up to (max + 1) bytes, not `await file.read()`
  in one call — an unbounded read would let a single request allocate
  memory proportional to whatever the client chooses to send, regardless of
  the max-size check that follows it.
"""
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.errors import AuthError

# (extension, servable content-type, magic-byte signature) — checked against
# the file's own first bytes, not the client-supplied Content-Type header.
_IMAGE_SIGNATURES: list[tuple[str, str, bytes]] = [
    (".jpg", "image/jpeg", b"\xff\xd8\xff"),
    (".png", "image/png", b"\x89PNG\r\n\x1a\n"),
    (".gif", "image/gif", b"GIF87a"),
    (".gif", "image/gif", b"GIF89a"),
    # WEBP is a RIFF container — bytes 0-3 are "RIFF", 8-11 are "WEBP";
    # checked as two separate anchored comparisons below, not one signature.
]
_WEBP_RIFF = b"RIFF"
_WEBP_TAG = b"WEBP"

_EMPLOYEE_PHOTO_SUBDIR = "employee_photos"


def _sniff_image_extension(header: bytes) -> str | None:
    for ext, _content_type, signature in _IMAGE_SIGNATURES:
        if header.startswith(signature):
            return ext
    if header[:4] == _WEBP_RIFF and header[8:12] == _WEBP_TAG:
        return ".webp"
    return None


async def _read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > max_bytes:
            raise AuthError(
                status_code=400,
                error_code="UPLOAD_TOO_LARGE",
                message=f"File exceeds the {max_bytes // (1024 * 1024)}MB upload limit.",
            )
    return bytes(chunks)


async def save_employee_photo(file: UploadFile, upload_dir: str, max_bytes: int) -> str:
    """Validates `file` is a real image (by content, not by name/header) and
    saves it under `<upload_dir>/employee_photos/<uuid><ext>`. Returns the
    URL it will be servable at (main.py mounts `upload_dir` at `/uploads`).
    """
    content = await _read_with_limit(file, max_bytes)
    if not content:
        raise AuthError(
            status_code=400, error_code="UPLOAD_EMPTY", message="Uploaded file is empty."
        )

    ext = _sniff_image_extension(content[:16])
    if ext is None:
        raise AuthError(
            status_code=400,
            error_code="UPLOAD_INVALID_IMAGE",
            message="File is not a recognized image format (JPEG, PNG, GIF, or WEBP).",
        )

    filename = f"{uuid.uuid4().hex}{ext}"
    directory = Path(upload_dir) / _EMPLOYEE_PHOTO_SUBDIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(content)

    return f"/uploads/{_EMPLOYEE_PHOTO_SUBDIR}/{filename}"
