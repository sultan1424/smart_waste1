"""
FastAPI dependencies — verifies Supabase JWT tokens.
"""
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import User

SUPABASE_URL  = "https://dovinauminsyyldhrymu.supabase.co"
SUPABASE_ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRvdmluYXVtaW5zeXlsZGhyeW11Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE3ODk3NjMsImV4cCI6MjA4NzM2NTc2M30.y76T02LY6oBCLOjYcqKohbCqb_gSKDA0QLbd686msCk"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": SUPABASE_ANON,
                },
            )

        if res.status_code != 200:
            raise credentials_exc
        supabase_user = res.json()
        auth_id = supabase_user.get("id")
      
        if not auth_id:
            raise credentials_exc
    except httpx.RequestError as e:
    
        raise credentials_exc

    result = await db.execute(
        select(User).where(User.auth_id == auth_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exc
    return user


def require_roles(*roles: str):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not authorized",
            )
        return current_user
    return checker