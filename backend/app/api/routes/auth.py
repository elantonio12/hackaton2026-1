import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class InviteRequest(BaseModel):
    name: str
    email: EmailStr
    role: Literal["admin", "collector"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserInfo(BaseModel):
    sub: str
    email: str
    name: str
    picture: str | None = None
    role: str = "citizen"

# ---------------------------------------------------------------------------
# In-memory user store (demo)
# ---------------------------------------------------------------------------

users_db: dict[str, dict] = {}
email_to_sub: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _create_jwt(data: dict, expires_minutes: int | None = None) -> str:
    exp = expires_minutes or settings.jwt_expiration_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=exp)
    payload = {**data, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        )

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = _decode_jwt(credentials.credentials)
    user = users_db.get(payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return user

# ---------------------------------------------------------------------------
# Seed default admin
# ---------------------------------------------------------------------------

def seed_admin():
    email = "admin@ecoruta.local"
    sub = f"local|{email}"
    if sub in users_db:
        return
    now = datetime.now(timezone.utc).isoformat()
    users_db[sub] = {
        "sub": sub,
        "email": email,
        "name": "Administrador",
        "picture": None,
        "role": "admin",
        "provider": "seed",
        "email_verified": True,
        "password_hash": _hash_password("admin123"),
        "created_at": now,
        "last_login": now,
    }
    email_to_sub[email] = sub
    logger.info("[Auth] Admin seed: %s / admin123", email)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    sub = email_to_sub.get(body.email.lower())
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contrasena incorrectos",
        )

    user = users_db[sub]

    if not user.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contrasena incorrectos",
        )

    if not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contrasena incorrectos",
        )

    user["last_login"] = datetime.now(timezone.utc).isoformat()
    access_token = _create_jwt({"sub": sub, "email": user["email"]})

    user_public = {k: v for k, v in user.items() if k != "password_hash"}
    return TokenResponse(access_token=access_token, user=user_public)


@router.post("/invite")
async def invite_user(body: InviteRequest, admin: dict = Depends(require_admin)):
    if body.email.lower() in email_to_sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo",
        )

    sub = f"local|{body.email.lower()}"
    now = datetime.now(timezone.utc).isoformat()
    temp_password = secrets.token_urlsafe(10)

    users_db[sub] = {
        "sub": sub,
        "email": body.email.lower(),
        "name": body.name,
        "picture": None,
        "role": body.role,
        "provider": "invite",
        "email_verified": True,
        "password_hash": _hash_password(temp_password),
        "created_at": now,
        "last_login": now,
    }
    email_to_sub[body.email.lower()] = sub

    logger.info("[Auth] User invited: %s (%s) by %s", body.email, body.role, admin["email"])

    return {
        "email": body.email.lower(),
        "name": body.name,
        "role": body.role,
        "temporary_password": temp_password,
    }


@router.get("/verify", response_model=UserInfo)
async def verify_token(user: dict = Depends(get_current_user)):
    return user


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    return {"status": "logged_out", "email": user.get("email")}


@router.get("/me", response_model=UserInfo)
async def me(user: dict = Depends(get_current_user)):
    return user
