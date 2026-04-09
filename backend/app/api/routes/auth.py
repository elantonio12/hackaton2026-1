import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User

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
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = _decode_jwt(credentials.credentials)
    sub = payload.get("sub")
    result = await db.execute(select(User).where(User.sub == sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return user


async def require_collector_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("collector", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de recolector o administrador",
        )
    return user

# ---------------------------------------------------------------------------
# Seed default admin
# ---------------------------------------------------------------------------

async def seed_admin(db: AsyncSession):
    email = "admin@ecoruta.app"
    sub = f"local|{email}"
    result = await db.execute(select(User).where(User.sub == sub))
    if result.scalar_one_or_none():
        return
    now = datetime.now(timezone.utc)
    db.add(User(
        sub=sub,
        email=email,
        name="Administrador",
        picture=None,
        role="admin",
        provider="seed",
        email_verified=True,
        password_hash=_hash_password("admin123"),
        created_at=now,
        last_login=now,
    ))
    await db.commit()
    logger.info("[Auth] Admin seed: %s / admin123", email)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contrasena incorrectos",
        )

    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contrasena incorrectos",
        )

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    access_token = _create_jwt({"sub": user.sub, "email": user.email})
    return TokenResponse(access_token=access_token, user=user.to_public_dict())


@router.post("/invite")
async def invite_user(
    body: InviteRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo",
        )

    sub = f"local|{body.email.lower()}"
    now = datetime.now(timezone.utc)
    temp_password = secrets.token_urlsafe(10)

    db.add(User(
        sub=sub,
        email=body.email.lower(),
        name=body.name,
        picture=None,
        role=body.role,
        provider="invite",
        email_verified=True,
        password_hash=_hash_password(temp_password),
        created_at=now,
        last_login=now,
    ))
    await db.commit()

    logger.info("[Auth] User invited: %s (%s) by %s", body.email, body.role, admin.email)

    return {
        "email": body.email.lower(),
        "name": body.name,
        "role": body.role,
        "temporary_password": temp_password,
    }


@router.get("/verify", response_model=UserInfo)
async def verify_token(user: User = Depends(get_current_user)):
    return user.to_public_dict()


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    return {"status": "logged_out", "email": user.email}


@router.get("/me", response_model=UserInfo)
async def me(user: User = Depends(get_current_user)):
    return user.to_public_dict()
