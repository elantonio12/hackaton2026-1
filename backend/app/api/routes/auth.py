from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.services.email import send_verification_email

router = APIRouter()
security = HTTPBearer()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GoogleLoginRequest(BaseModel):
    """Body that the frontend sends after Google Sign-In."""
    token: str


class RegisterRequest(BaseModel):
    """Body for email/password registration."""
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """Body for email/password login."""
    email: EmailStr
    password: str


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
            detail="Token inválido o expirado",
        )

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Decode JWT and return the stored user."""
    payload = _decode_jwt(credentials.credentials)
    user = users_db.get(payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user

# ---------------------------------------------------------------------------
# Email/Password endpoints
# ---------------------------------------------------------------------------

@router.post("/register")
async def register(body: RegisterRequest):
    """Register a new user. Sends verification email if Resend is configured."""
    if body.email.lower() in email_to_sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo electrónico",
        )

    sub = f"local|{body.email.lower()}"
    now = datetime.now(timezone.utc).isoformat()

    users_db[sub] = {
        "sub": sub,
        "email": body.email.lower(),
        "name": body.name,
        "picture": None,
        "role": "citizen",
        "provider": "email",
        "email_verified": False,
        "password_hash": _hash_password(body.password),
        "created_at": now,
        "last_login": now,
    }
    email_to_sub[body.email.lower()] = sub

    # Send verification email
    verification_token = _create_jwt(
        {"sub": sub, "purpose": "email_verification"},
        expires_minutes=60 * 24,  # 24 hours
    )
    verification_url = f"{settings.frontend_url}/auth/verified?token={verification_token}"
    email_sent = send_verification_email(body.email, body.name, verification_url)

    if email_sent:
        return {
            "status": "verification_pending",
            "message": "Se envió un correo de verificación. Revisa tu bandeja de entrada.",
            "email": body.email.lower(),
        }

    # Fallback: if email service is not configured, auto-verify and return token
    users_db[sub]["email_verified"] = True
    access_token = _create_jwt({"sub": sub, "email": body.email.lower()})
    user_public = {k: v for k, v in users_db[sub].items() if k != "password_hash"}
    return TokenResponse(access_token=access_token, user=user_public)


@router.get("/verify-email")
async def verify_email(token: str = Query(...)):
    """Verify a user's email from the link sent to their inbox."""
    payload = _decode_jwt(token)

    if payload.get("purpose") != "email_verification":
        raise HTTPException(status_code=400, detail="Token inválido")

    sub = payload.get("sub")
    user = users_db.get(sub)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.get("email_verified"):
        return {"status": "already_verified", "message": "Esta cuenta ya fue verificada."}

    user["email_verified"] = True
    access_token = _create_jwt({"sub": sub, "email": user["email"]})

    user_public = {k: v for k, v in user.items() if k != "password_hash"}
    return {
        "status": "verified",
        "message": "¡Cuenta verificada exitosamente!",
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_public,
    }


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate with email and password."""
    sub = email_to_sub.get(body.email.lower())
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )

    user = users_db[sub]

    if not user.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esta cuenta usa Google Sign-In. Inicia sesión con Google.",
        )

    if not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )

    if not user.get("email_verified", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta no verificada. Revisa tu correo electrónico.",
        )

    user["last_login"] = datetime.now(timezone.utc).isoformat()
    access_token = _create_jwt({"sub": sub, "email": user["email"]})

    user_public = {k: v for k, v in user.items() if k != "password_hash"}
    return TokenResponse(access_token=access_token, user=user_public)

# ---------------------------------------------------------------------------
# Google OAuth endpoint
# ---------------------------------------------------------------------------

@router.post("/google", response_model=TokenResponse)
async def google_login(body: GoogleLoginRequest):
    """Verify a Google ID-token and return a JWT for the app."""
    try:
        idinfo = google_id_token.verify_oauth2_token(
            body.token,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de Google inválido",
        )

    sub = idinfo["sub"]
    email = idinfo.get("email", "")
    now = datetime.now(timezone.utc).isoformat()

    if sub not in users_db:
        users_db[sub] = {
            "sub": sub,
            "email": email,
            "name": idinfo.get("name", ""),
            "picture": idinfo.get("picture"),
            "role": "citizen",
            "provider": "google",
            "email_verified": True,  # Google accounts are pre-verified
            "created_at": now,
        }
        if email:
            email_to_sub[email.lower()] = sub

    users_db[sub]["last_login"] = now
    access_token = _create_jwt({"sub": sub, "email": email})

    return TokenResponse(access_token=access_token, user=users_db[sub])

# ---------------------------------------------------------------------------
# Protected endpoints
# ---------------------------------------------------------------------------

@router.get("/verify", response_model=UserInfo)
async def verify_token(user: dict = Depends(get_current_user)):
    """Verify that a JWT is still valid and return the user."""
    return user


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Logout (client should discard the token)."""
    return {"status": "logged_out", "email": user.get("email")}


@router.get("/me", response_model=UserInfo)
async def me(user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return user
