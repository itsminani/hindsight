"""Opaque, prefixed IDs like "pf_7Kq2..." (Ch2: identifiers are opaque and never reused)."""

import secrets
import string

_ALPHABET = string.ascii_letters + string.digits
_LENGTH = 16  # 62^16 ≈ 4.7e28 possible values: unguessable, and collisions are not a real risk

PREFIXES = {"user": "us", "plan": "pl", "portfolio": "pf", "position": "ps", "report": "rp", "job": "jb"}


def new_id(kind: str) -> str:
    """Return a new random ID for a kind of object, e.g. new_id("portfolio") -> "pf_aZ3...".

    Random instead of 1, 2, 3 so nobody can guess other people's IDs by counting.
    """
    random_part = "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
    return f"{PREFIXES[kind]}_{random_part}"
