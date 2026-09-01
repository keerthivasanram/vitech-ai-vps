"""Password and token hashing — standard library only.

`hashlib.scrypt` is memory-hard and ships with Python, so this adds no
dependency to a stack the production review already flagged as under-pinned.
Parameters follow the interactive-login end of the usual recommendations
(N=2^15, r=8, p=1 ≈ 32 MB, tens of milliseconds), which is the right trade for
a login that a human waits on.

Secrets are compared with `hmac.compare_digest` throughout. A plain `==` on a
hash leaks timing, and the whole point of hashing is that the comparison is the
only thing an attacker can reach.
"""
import base64
import hashlib
import hmac
import secrets

_N = 2 ** 15
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def new_salt() -> str:
    return base64.b64encode(secrets.token_bytes(_SALT_BYTES)).decode()


def hash_password(password: str, salt: str) -> str:
    """scrypt hash of a password, base64-encoded."""
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=base64.b64decode(salt),
        n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=64 * 1024 * 1024)
    return base64.b64encode(digest).decode()


def verify_password(password: str, salt: str, expected: str) -> bool:
    """Constant-time check. Never raises on malformed stored values."""
    try:
        return hmac.compare_digest(hash_password(password, salt), expected)
    except Exception:
        return False


# --- opaque bearer tokens ---------------------------------------------------
# Session and service tokens are random, not derived from anything, so they need
# no salt: they are stored as a plain SHA-256 so a database read cannot be
# replayed as a credential.

def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(token_hash(token), expected_hash or "")
