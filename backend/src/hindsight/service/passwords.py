"""Password hashing with Argon2id (OWASP's first choice for storing passwords).

We never store a password, only a salted, slow hash of it. Checking a password means hashing
the attempt the same way and comparing.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash (it includes its own random salt and settings)."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True if the password matches the hash, False otherwise (never raises for a wrong password)."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False
