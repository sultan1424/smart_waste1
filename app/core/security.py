"""
Security helpers:
- JWT creation + verification
- AES-256-GCM encrypt/decrypt (for sensitive fields at rest)
- Password hashing (bcrypt)

AES-256-GCM is used instead of Fernet (which is AES-128).
We encrypt the `email` field in the users table as a demonstration
of AES-256 encryption at rest per the security spec.
"""
import os, base64, json
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

# ── Password hashing ──────────────────────────────────────────────────────
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

# ── JWT ───────────────────────────────────────────────────────────────────
ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])

# ── AES-256-GCM encryption at rest ───────────────────────────────────────
# Encrypted fields: users.email
# Why: email is PII; demonstrating AES-256-GCM compliance per spec.
# Key stored in AES_256_KEY env var (never hardcoded).

def _get_aes_key() -> bytes:
    key = settings.AES_256_KEY
    if not key:
        # Dev fallback — generate ephemeral key (data lost on restart)
        return os.urandom(32)
    raw = base64.b64decode(key)
    if len(raw) != 32:
        raise ValueError("AES_256_KEY must be exactly 32 bytes (base64-encoded)")
    return raw

def encrypt_value(plaintext: str) -> str:
    """Encrypt a string using AES-256-GCM. Returns base64(nonce + ciphertext)."""
    key   = _get_aes_key()
    aesgcm= AESGCM(key)
    nonce = os.urandom(12)          # 96-bit nonce recommended for GCM
    ct    = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()

def decrypt_value(encrypted: str) -> str:
    """Decrypt a value encrypted with encrypt_value()."""
    key    = _get_aes_key()
    aesgcm = AESGCM(key)
    raw    = base64.b64decode(encrypted)
    nonce  = raw[:12]
    ct     = raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()