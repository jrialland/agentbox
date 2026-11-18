import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.security import create_jwt, hash_password, verify_password
from agentbox_models.tables.auth import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str


class MeResponse(BaseModel):
    id: str
    username: str
    permissions: list[str]


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    factory = request.app.state.session_factory
    async with factory() as s:
        user = (
            await s.execute(select(User).where(User.username == body.username))
        ).scalars().first()
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    settings = request.app.state.settings
    token = create_jwt(
        user.id,
        settings.jwt_secret.get_secret_value(),
        settings.jwt_algorithm,
        settings.jwt_expiry_seconds,
    )
    return {"access_token": token, "token_type": "bearer"}  # nosec B105


@router.post("/register")
async def register(body: RegisterRequest, request: Request):
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
    return {"id": user.id, "username": user.username}


@router.get("/me", response_model=MeResponse)
async def me(request: Request):
    if not request.user.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": request.user.identity,
        "username": request.user.display_name,
        "permissions": list(request.auth.scopes) if request.auth else [],
    }
