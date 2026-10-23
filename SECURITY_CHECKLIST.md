# Security checklist — Authentication & Token Management

Intern verification: 14 Aug 2026. Mentor sign-off still required before merge.

## Secrets and storage

- [x] JWT secret and database password are only in `.env`, not in source
- [x] `.env` is gitignored
- [x] `.env.example` has placeholders only
- [x] Application fails to start if `JWT_SECRET_KEY` is missing or shorter than 32 characters
- [x] Passwords are stored only as bcrypt hashes
- [x] Refresh tokens are stored only as SHA-256 hashes
- [x] Access logs do not contain passwords, tokens, JWT secrets, or Authorization headers

## Token behaviour

- [x] Access JWT includes `sub`, `user_id`, `roles`, `company_id`, `jti`, `iat`, `exp`, `token_type`
- [x] Tokens do not include passwords or sensitive profile data
- [x] Expired, malformed, wrongly signed, and wrong-type tokens return 401
- [x] Missing `sub`/`jti` claims return 401
- [x] Logout puts the access `jti` on `revoked_tokens` and revokes the session
- [x] Refresh rotates the session; revoked/expired refresh tokens are rejected



## API and sessions

- [x] Login uses the same generic message for unknown email, wrong password, inactive, and locked accounts
- [x] Protected routes use the reusable Bearer dependency
- [x] Only `Authorization: Bearer <token>` is accepted
- [x] Each login creates an `auth_sessions` row with expiry and optional IP/user-agent
- [x] `/auth/me` updates `last_used_at` for the current session



## Tests and review

- [x] `pytest app/tests` passes
- [x] Alembic upgrade and downgrade work in the development database (`e4a1b8c2d066` round-trip)
- [ ] Senior developer has reviewed security-sensitive code

## ⚠️ Known prototype-only risk — Employee PII (Module 4)

- [x] **Done.** `employees.bank_account_number`, `bank_ifsc`, `pan_number`,
      `aadhaar_number`, `phone_number`, `residence_proof_reference`, and
      `photo_reference` are encrypted at rest (Fernet, via
      `app/database/encrypted_types.py` + `app/core/pii_crypto.py`) whenever
      `PII_ENCRYPTION_KEY` is set in the environment. Reads/writes through
      the ORM (including API responses) stay plain text automatically —
      only the DB column itself holds ciphertext.
- [ ] **Remaining gap:** `PII_ENCRYPTION_KEY` is optional, not enforced at
      startup — an environment that never sets it silently stores these
      fields in plaintext (a one-time warning log is the only signal; see
      `app/core/pii_crypto.py`). Before production: make the key required,
      or fail startup loudly when it's missing.
- [ ] **Remaining gap:** rows written *before* encryption was enabled are
      **not** retroactively re-encrypted — only re-encrypted the next time
      each row is written. A one-time backfill script is still outstanding.
- `residence_proof_reference` stores a filename/URL only — no actual file
  upload/storage exists for it yet. `photo_reference` is the exception: see
  "Employee photo upload" below — it now has real upload/storage support.

## ⚠️ Known prototype-only risk — Employee photo upload

- [x] Upload validates the file is a real image by its **content** (magic
      number), not by the client-supplied filename or `Content-Type` header
      — both are attacker-controlled. See `app/core/uploads.py` and
      `test_employee_photo_upload.py`'s renamed-executable test.
- [x] Saved filename is always a freshly generated UUID, never derived from
      the client's filename — no path-traversal surface from it.
- [x] Upload size is capped (`UPLOAD_MAX_BYTES`, default 5MB) and enforced
      while reading, not after — an oversized request can't be fully
      buffered into memory first.
- [ ] **NOT DONE — flagged, not fixed.** Uploaded photos are served from
      `/uploads/...` as **plain static files, with no authentication** (see
      `main.py`'s `StaticFiles` mount) — anyone with a photo's URL can view
      it without logging in. Acceptable for a prototype where the URL
      itself is an unguessable UUID and the content is "a photo", not a
      secret; **not** acceptable if this pattern is later reused for a
      genuinely sensitive file (e.g. `residence_proof_reference`) without
      first adding an authenticated read path.
- [ ] **Remaining gap:** no antivirus/malware scanning of uploaded content
      — only file-type validation. Fine for a prototype; a real deployment
      accepting user uploads should scan them.

Mentor: ______________________  Date: __________