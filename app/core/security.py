"""Password + token hashing helpers.

We intentionally use PBKDF2-SHA256 instead of bcrypt.

Why:
- bcrypt has a hard 72-byte password limit.
- passlib's bcrypt integration frequently breaks when the upstream `bcrypt`
  package changes its internals.

PBKDF2-SHA256 avoids both issues and is widely supported.
"""

import secrets
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    # Never store tokens in plaintext.
    return pwd_context.hash(token)


def verify_token(token: str, token_hash: str) -> bool:
    return pwd_context.verify(token, token_hash)
