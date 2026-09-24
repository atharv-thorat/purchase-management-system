from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFound, Unauthorized
from app.core.security import create_access_token, verify_password
from app.models.enums import Role
from app.models.master import User
from app.schemas.auth import DemoUsersResponse, LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Login-page button order: follows the P2P flow.
_ROLE_ORDER = list(Role)


def _authenticate(db, email: str, password: str) -> User:
    user = db.scalar(
        select(User).options(joinedload(User.department)).where(func.lower(User.email) == email.strip().lower())
    )
    if user is None or not verify_password(password, user.password_hash):
        raise Unauthorized("Incorrect email or password", code="INVALID_CREDENTIALS")
    if not user.is_active:
        raise Unauthorized("This account has been deactivated", code="USER_INACTIVE")
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    """JSON login used by the frontend."""
    user = _authenticate(db, body.email, body.password)
    token, expires_in = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


class OAuthToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=OAuthToken, include_in_schema=False)
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> OAuthToken:
    """Form login for Swagger's Authorize dialog: username = email, password = demo123."""
    user = _authenticate(db, form.username, form.password)
    return OAuthToken(access_token=create_access_token(user.id, user.role)[0])


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.get("/demo-users", response_model=DemoUsersResponse)
def demo_users(db: DbSession) -> DemoUsersResponse:
    """Seeded accounts for the one-click login buttons. Disabled unless PMS_DEMO_MODE is on."""
    if not settings.demo_mode:
        raise NotFound("Not found")
    users = db.scalars(
        select(User).options(joinedload(User.department)).where(User.is_active.is_(True))
    ).all()
    users = sorted(users, key=lambda u: (_ROLE_ORDER.index(u.role), u.department.name if u.department else ""))
    return DemoUsersResponse(password=settings.demo_password, users=[UserOut.model_validate(u) for u in users])
