"""
Authorization module for Public API

Only API Key authentication (no JWT, no admin login).
"""

from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

try:
    from config import API_KEY
except Exception as e:
    raise RuntimeError(
        'Failed to import configuration. Ensure app/config.py is importable and required env vars are set.'
    ) from e

# Security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> bool:
    """
    Verify static API key from X-API-Key header

    Used for public endpoints (GET requests)
    """
    if api_key is None or api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API Key"
        )
    return True


def verify_api_key_query(api_key: Optional[str] = None) -> bool:
    """
    Verify static API key from query parameter

    Used for audio endpoint (browser cannot send custom headers)
    """
    if api_key is None or api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API Key"
        )
    return True


# Dependencies for use in endpoints
RequireAPIKey = Depends(verify_api_key)
