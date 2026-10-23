"""SQLAlchemy column type that transparently encrypts/decrypts at the ORM
boundary (Foundation Core PII protection — see app/core/pii_crypto.py).

Using a TypeDecorator instead of hand-rolling encrypt/decrypt calls in
employee_service.py keeps every read/write path automatically covered
(model attribute access, `EmployeeResponse.model_validate(employee)`,
future service functions) without having to remember to call
encrypt/decrypt at every call site — the model column is the single place
this rule lives, matching this codebase's existing preference for one
centralized mechanism over scattered per-call handling.
"""
from sqlalchemy.types import Text, TypeDecorator

from app.core.pii_crypto import decrypt_value, encrypt_value


class EncryptedString(TypeDecorator):
    """Stores TEXT ciphertext in the DB; the Python-side value is always
    plain text. Backed by Text (not a bounded VARCHAR) because a Fernet
    token is meaningfully longer than the original short PII values (e.g. a
    10-character PAN number becomes ~130 base64 characters once encrypted).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_value(value)
