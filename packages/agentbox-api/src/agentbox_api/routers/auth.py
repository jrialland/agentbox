"""Authentication endpoints for obtaining and inspecting a bearer token."""

import uuid

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.security import create_jwt, hash_password, verify_password
from agentbox_models.tables.auth import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Credentials exchanged for a bearer token."""

    username: str
    password: str


class RegisterRequest(BaseModel):
    """Fields needed to register a new account."""

    username: str
    email: str
    password: str


class LoginResponse(BaseModel):
    """A bearer token and its type."""

    access_token: str
    token_type: str


class MeResponse(BaseModel):
    """The authenticated user's identity and effective permission scopes."""

    id: str
    username: str
    permissions: list[str]


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    """Exchange username and password for a bearer token.

    Returns:
        A token response, or 401 when the credentials are invalid.
    """
    factory = request.app.state.session_factory
    async with factory() as s:
        user = (
            await s.execute(select(User).where(User.username == body.username))
        ).scalars().first()
        if user is None or not verify_password(body.password, user.password_hash):
            logger.warning("login failed user={}", body.username)
            raise HTTPException(status_code=401, detail="Invalid credentials")
    settings = request.app.state.settings
    token = create_jwt(
        user.id,
        settings.jwt_secret.get_secret_value(),
        settings.jwt_algorithm,
        settings.jwt_expiry_seconds,
    )
    logger.info("login ok user={}", user.username)
    return {"access_token": token, "token_type": "bearer"}  # nosec B105


@router.post("/register")
async def register(body: RegisterRequest, request: Request):
    """Register a new user account.

    Returns:
        The new user's id and username.
    """
    factory = request.app.state.session_factory
    async with factory() as s:
        user = User(
            id=uuid.uuid4().hex,
            username=body.username,
            email=body.email,
            password_hash=hash_password(body.password),
        )
        s.add(user)
        await s.commit()
    logger.info("registered user={}", user.username)
    return {"id": user.id, "username": user.username}


@router.get("/me", response_model=MeResponse)
async def me(request: Request):
    """Return the authenticated user and its permission scopes.

    Returns:
        The caller's identity and effective scopes, or 401 when unauthenticated.
    """
    if not request.user.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": request.user.identity,
        "username": request.user.display_name,
        "permissions": list(request.auth.scopes) if request.auth else [],
    }
