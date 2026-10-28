"""Generate an RSA key pair for JWT_ALGORITHM=RS256.

    python scripts/generate_jwt_keys.py [directory]      (default: keys/)

Writes jwt_private.pem and jwt_public.pem and prints the settings to put in
.env. Never overwrites an existing file. Keep the private key out of git and
out of images; only the public key (or /.well-known/jwks.json) is ever shared
with services that verify tokens.

Rotating: generate a new pair, point JWT_PRIVATE_KEY_PATH at it, and list the
old public key in JWT_PREVIOUS_PUBLIC_KEY_PATHS until its tokens have expired
(REFRESH_TOKEN_EXPIRE_DAYS).
"""
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_BITS = 3072


def main(argv: list[str]) -> int:
    directory = Path(argv[1] if len(argv) > 1 else "keys")
    private_path = directory / "jwt_private.pem"
    public_path = directory / "jwt_public.pem"
    existing = [p for p in (private_path, public_path) if p.exists()]
    if existing:
        print(f"Refusing to overwrite: {', '.join(str(p) for p in existing)}", file=sys.stderr)
        return 1

    directory.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    try:
        os.chmod(private_path, 0o600)  # no effect on Windows; harmless there
    except OSError:
        pass

    print(f"Wrote {private_path} and {public_path}")
    print("\nAdd to .env:")
    print("JWT_ALGORITHM=RS256")
    print(f"JWT_PRIVATE_KEY_PATH={private_path}")
    print(f"JWT_PUBLIC_KEY_PATH={public_path}")
    print(
        "\nTokens signed with the old shared secret keep verifying while "
        "JWT_SECRET_KEY / JWT_PREVIOUS_SECRET_KEYS stay set; remove them after "
        "REFRESH_TOKEN_EXPIRE_DAYS."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
