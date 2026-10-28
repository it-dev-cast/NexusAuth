import bcrypt

# bcrypt only ever looks at the first 72 BYTES of a password, and bcrypt 5
# refuses longer input with a ValueError instead of truncating it.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        # New passwords are checked against the policy (app/schemas/auth.py)
        # before they get here; this keeps a caller that skips it from
        # silently storing a truncated password.
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")

    salt = bcrypt.gensalt()

    hashed_password = bcrypt.hashpw(
        password_bytes,
        salt,
    )

    return hashed_password.decode("utf-8")


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        # No stored password can be this long (the policy caps them), so it
        # can never match — a plain "wrong password", not a server error.
        # The comparison still runs on the first 72 bytes so a too-long
        # attempt costs the same time as any other wrong one.
        bcrypt.checkpw(password_bytes[:MAX_PASSWORD_BYTES], hashed_password.encode("utf-8"))
        return False
    return bcrypt.checkpw(
        password_bytes,
        hashed_password.encode("utf-8"),
    )
