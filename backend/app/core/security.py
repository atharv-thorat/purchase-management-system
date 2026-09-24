"""Password hashing (bcrypt) and JWT encode/decode."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # malformed hash
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    """Returns (token, lifetime in seconds). The role claim is informational only; every
    request re-reads the user so deactivation and role changes apply immediately."""
    lifetime = timedelta(minutes=settings.access_token_minutes)
    issued = datetime.now(UTC)
    payload = {"sub": str(user_id), "role": role, "iat": issued, "exp": issued + lifetime}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> int:
    """Returns the user id. Raises jwt.InvalidTokenError on a bad or expired token."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp"]},
    )
    return int(payload["sub"])
