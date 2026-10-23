from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


def _headers_with_role(role: str):
    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    db.commit()
    db.close()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    access = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access}"}


def _admin_headers():
    return _headers_with_role("admin")


# Minimal byte sequences carrying just the magic number app/core/uploads.py
# actually checks for — none of these are a fully valid, decodable image,
# but that's the point: the sniff only looks at the signature, so this is
# exactly the boundary it's meant to accept/reject on.
_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_GIF_BYTES = b"GIF89a" + b"\x00" * 32
_WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32
_NOT_AN_IMAGE = b"just some plain text, not an image at all, padded out"
# A Windows PE header (starts "MZ") — proves the sniff rejects a
# non-image file even when it's renamed with an image extension and the
# client claims an image Content-Type; both are attacker-controlled and
# neither is what app/core/uploads.py actually checks.
_FAKE_EXE_AS_JPEG = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 32


def test_upload_accepts_jpeg():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/uploads/employee-photo",
        files={"file": ("photo.jpg", _JPEG_BYTES, "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 201
    url = response.json()["data"]["url"]
    assert url.startswith("/uploads/employee_photos/")
    assert url.endswith(".jpg")


def test_upload_accepts_png_gif_webp():
    headers = _admin_headers()
    for filename, content, ext in [
        ("photo.png", _PNG_BYTES, ".png"),
        ("photo.gif", _GIF_BYTES, ".gif"),
        ("photo.webp", _WEBP_BYTES, ".webp"),
    ]:
        response = client.post(
            "/api/v1/uploads/employee-photo",
            files={"file": (filename, content, "application/octet-stream")},
            headers=headers,
        )
        assert response.status_code == 201, filename
        assert response.json()["data"]["url"].endswith(ext)


def test_upload_rejects_non_image_content():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/uploads/employee-photo",
        files={"file": ("notes.txt", _NOT_AN_IMAGE, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "UPLOAD_INVALID_IMAGE"


def test_upload_rejects_renamed_executable_despite_image_extension_and_content_type():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/uploads/employee-photo",
        files={"file": ("totally-a-photo.jpg", _FAKE_EXE_AS_JPEG, "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "UPLOAD_INVALID_IMAGE"


def test_upload_rejects_empty_file():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/uploads/employee-photo",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "UPLOAD_EMPTY"


def test_upload_rejects_file_over_size_limit():
    headers = _admin_headers()
    oversized = _JPEG_BYTES + b"0" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/api/v1/uploads/employee-photo",
        files={"file": ("big.jpg", oversized, "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "UPLOAD_TOO_LARGE"


def test_upload_requires_employee_write_permission():
    reader_headers = _headers_with_role("read_only")
    response = client.post(
        "/api/v1/uploads/employee-photo",
        files={"file": ("photo.jpg", _JPEG_BYTES, "image/jpeg")},
        headers=reader_headers,
    )
    assert response.status_code == 403


def test_uploaded_photo_is_servable_and_usable_as_employee_photo_reference():
    headers = _admin_headers()
    upload = client.post(
        "/api/v1/uploads/employee-photo",
        files={"file": ("photo.jpg", _JPEG_BYTES, "image/jpeg")},
        headers=headers,
    )
    url = upload.json()["data"]["url"]

    # Actually servable back, not just a URL string that was never written.
    served = client.get(url)
    assert served.status_code == 200
    assert served.content == _JPEG_BYTES

    # And it round-trips as an Employee's photo_reference exactly like a
    # manually-typed URL always could — the upload only changes how the
    # URL is obtained, not what the Employee API accepts.
    company = client.post(
        "/api/v1/companies",
        json={
            "name": f"Acme {unique_word()}",
            "address": "123 Test Street",
            "contact_email": "contact@example.com",
        },
        headers=headers,
    )
    company_id = company.json()["data"]["id"]
    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Photo",
            "last_name": "Test",
            "email": unique_email(),
            "photo_reference": url,
        },
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["data"]["photo_reference"] == url
