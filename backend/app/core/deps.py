"""Request dependencies: the current user and role gates."""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.models.enums import Role
from app.models.master import User

# Bearer tokens. tokenUrl lets Swagger's "Authorize" dialog log in with email + password.
_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(_bearer)],
) -> User:
    if not token:
        raise Unauthorized("Not authenticated")
    try:
        user_id = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Session expired, please log in again", code="TOKEN_EXPIRED") from None
    except (jwt.InvalidTokenError, ValueError):
        raise Unauthorized("Invalid token") from None

    user = db.get(User, user_id, options=[joinedload(User.department)])
    if user is None or not user.is_active:
        raise Unauthorized("User is inactive or no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[..., User]:
    """Dependency allowing only the given roles.

    Transactional endpoints never list ADMIN, which keeps ADMIN read-only (D-09).
    Usage: `user: Annotated[User, Depends(require_roles(Role.PURCHASE))]`.
    """
    allowed = frozenset(roles)

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            names = ", ".join(sorted(r.value for r in allowed))
            needed = f"role {names}" if len(allowed) == 1 else f"one of the roles {names}"
            raise Forbidden(f"This action requires {needed}; you are {user.role}")
        return user

    return dependency
