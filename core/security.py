import os
import logging
from typing import Optional
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from cryptography.fernet import Fernet

logger = logging.getLogger("security")

# ─────────────────────────────────────────────────────────────
# Encryption Configuration
# ─────────────────────────────────────────────────────────────
# We attempt to load the master encryption key from environment.
# If not present, we generate a transient key. In production,
# this key should be statically defined in deployment config / vault.
_MASTER_KEY = os.getenv("BYOK_ENCRYPTION_KEY")

if not _MASTER_KEY:
    # Generate a transient key for development/fallback
    logger.warning("BYOK_ENCRYPTION_KEY not set in environment! Generating a transient key for session.")
    _MASTER_KEY = Fernet.generate_key().decode()
else:
    # Ensure it's valid base64 key
    try:
        Fernet(_MASTER_KEY.encode())
    except Exception as ex:
        logger.error(f"Provided BYOK_ENCRYPTION_KEY is invalid! Generating fallback: {ex}")
        _MASTER_KEY = Fernet.generate_key().decode()

class EncryptionUtility:
    """
    Utility class for secure encryption and decryption of API keys using Fernet (AES-128 in CBC with HMAC-SHA256).
    """
    _cipher = Fernet(_MASTER_KEY.encode())

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """
        Encrypts a plaintext string and returns a base64 string representation.
        """
        if not plaintext:
            raise ValueError("Cannot encrypt an empty string")
        encrypted_bytes = cls._cipher.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """
        Decrypts a ciphertext base64 string and returns the plaintext string.
        """
        if not ciphertext:
            raise ValueError("Cannot decrypt empty ciphertext")
        try:
            decrypted_bytes = cls._cipher.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error("Failed to decrypt data. The encryption key might be incorrect or corrupted.")
            raise ValueError("Decryption failed. Invalid encryption key or corrupted data.") from e


# ─────────────────────────────────────────────────────────────
# User Authentication Dependency
# ─────────────────────────────────────────────────────────────
security_bearer = HTTPBearer(auto_error=False)

async def get_current_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)
) -> str:
    """
    FastAPI dependency injection pattern to retrieve the current user or session context.
    
    Order of resolution:
    1. Authorization Bearer token (e.g. "Bearer user_123")
    2. X-User-ID request header
    3. JSON request body 'session_id' (if body contains json)
    4. Query parameters 'session_id'
    
    If no identifier can be resolved, raises HTTP 401.
    """
    # 1. Check Bearer Token
    if credentials:
        token = credentials.credentials.strip()
        # In a real system, we would parse/verify JWT token. Here, we extract the identity string directly.
        if token:
            return token

    # 2. Check X-User-ID Header
    user_id_header = request.headers.get("x-user-id") or request.headers.get("X-User-ID")
    if user_id_header:
        return user_id_header.strip()

    # 3. Check JSON body for session_id or user_id
    try:
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.json()
            if isinstance(body, dict):
                sid = body.get("session_id") or body.get("user_id")
                if sid:
                    return str(sid).strip()
    except Exception:
        # Request body may not be JSON or may have already been consumed
        pass

    # 4. Check Query Parameters for session_id or user_id
    query_params = request.query_params
    sid = query_params.get("session_id") or query_params.get("user_id")
    if sid:
        return str(sid).strip()

    # If all resolutions fail, raise 401 Unauthorized
    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Missing or invalid authentication token, X-User-ID header, or session_id."
    )
