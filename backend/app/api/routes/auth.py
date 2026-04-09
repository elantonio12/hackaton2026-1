from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()
security = HTTPBearer()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GoogleLoginRequest(BaseModel):
    """Body that the frontend sends after Google Sign-In."""
    token: str  # Google ID-token (credential from Google Sign-In)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserInfo(BaseModel):
    sub: str
    email: str
    name: str
    picture: str | None = None

# ---------------------------------------------------------------------------
# In-memory user store (demo)
# ---------------------------------------------------------------------------

users_db: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_jwt(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
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
# Endpoints
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
    now = datetime.now(timezone.utc).isoformat()

    if sub not in users_db:
        users_db[sub] = {
            "sub": sub,
            "email": idinfo.get("email", ""),
            "name": idinfo.get("name", ""),
            "picture": idinfo.get("picture"),
            "created_at": now,
        }
    users_db[sub]["last_login"] = now

    access_token = _create_jwt({"sub": sub, "email": users_db[sub]["email"]})

    return TokenResponse(access_token=access_token, user=users_db[sub])


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
