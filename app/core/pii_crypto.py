"""Field-level encryption at rest for Employee PII (Foundation Core Module 4
+ SECURITY_CHECKLIST.md's flagged, previously-unfixed risk).

bank_account_number / bank_ifsc / pan_number / aadhaar_number /
residence_proof_reference / photo_reference were stored as plain text
columns. This module provides the encrypt/decrypt primitive; the actual
transparent-at-the-ORM-layer wiring is in app/database/encrypted_types.py.

Deliberately graceful, not a hard startup requirement: `PII_ENCRYPTION_KEY`
is optional. If it's not configured, encryption is simply disabled (fields
stay plain text, exactly like today) rather than crashing every existing
deployment/test that hasn't set this new variable yet. What *is* loud is
the one-time startup warning below — silence would be the actual security
problem, not the missing key itself. See SECURITY_CHECKLIST.md for the
migration-completeness caveat (existing plaintext rows aren't
retroactively re-encrypted by this change; only new writes are).
"""
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger("nexusauth.pii")

_warned_missing_key = False


def get_fernet() -> Fernet | None:
    settings = get_settings()
    key = settings.pii_encryption_key
    if not key:
        global _warned_missing_key
        if not _warned_missing_key:
            logger.warning(
                "PII_ENCRYPTION_KEY is not set — employee PII fields "
                "(bank account, IFSC, PAN, Aadhaar, phone number, document "
                "references) will be stored in PLAINTEXT. Set "
                "PII_ENCRYPTION_KEY (a Fernet key, e.g. Fernet.generate_key()) "
                "to enable encryption at rest."
            )
            _warned_missing_key = True
        return None
    return Fernet(key.encode("utf-8"))


def encrypt_value(value: str) -> str:
    fernet = get_fernet()
    if fernet is None:
        return value
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str) -> str:
    fernet = get_fernet()
    if fernet is None:
        return value
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Legacy plaintext row written before encryption was enabled (or a
        # rotated/mismatched key) — surface the stored value as-is rather
        # than crashing the read. Documented residual gap: such rows are
        # not automatically re-encrypted; only re-encrypted on next write.
        return value
