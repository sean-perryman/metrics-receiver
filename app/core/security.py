import secrets
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    # Use bcrypt so we never store tokens in plaintext.
    return pwd_context.hash(token)


def verify_token(token: str, token_hash: str) -> bool:
    return pwd_context.verify(token, token_hash)
