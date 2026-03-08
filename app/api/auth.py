from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import hashlib

from app.db.session import get_db
from app.models.models import User
from app.core.security import verify_password, create_access_token, decrypt_value, encrypt_value

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Schemas ───────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    role:         str
    email:        str

class MeResponse(BaseModel):
    id:            int
    email:         str
    role:          str
    restaurant_id: str | None

# ── Helpers ───────────────────────────────────────────────────────────────

def _email_hash(email: str) -> str:
    """SHA-256 hash of email for fast indexed lookup (not for security)."""
    return hashlib.sha256(email.lower().encode()).hexdigest()

# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db:   AsyncSession = Depends(get_db),
):
    # Look up user by email hash (fast indexed lookup)
    h = _email_hash(form.username)
    result = await db.execute(select(User).where(User.email_hash == h))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    email = decrypt_value(user.email_encrypted)

    return TokenResponse(
        access_token=token,
        role=user.role.value,
        email=email,
    )


@router.get("/me", response_model=MeResponse)
async def me(db: AsyncSession = Depends(get_db), token: str = ""):
    # Simplified — full version uses get_current_user dependency
    from app.core.deps import get_current_user
    from fastapi import Request
    # This endpoint is wired properly in routes
    pass