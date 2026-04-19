from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import hashlib

from app.db.session import get_db
from app.models.models import User
from app.core.security import verify_password, create_access_token, decrypt_value
from app.core.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    role:         str
    email:        str

def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()

@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db:   AsyncSession = Depends(get_db),
):
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

@router.get("/me", response_model=None)
async def me(current_user: User = Depends(get_current_user)):
    return {
        "role": current_user.role.value,
        "id": current_user.id,
    }
    